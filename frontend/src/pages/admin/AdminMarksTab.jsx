import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Award, Plus, Edit2, Trash2, CheckCircle2, AlertCircle,
  Upload, Download, FileSpreadsheet, RefreshCw, X, ChevronRight,
  Eye, AlertTriangle, ShieldAlert, Check, HelpCircle
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { classMarksAPI } from '../../api/client';

export default function AdminMarksTab({ cohorts, institution }) {
  const [selectedCohortId, setSelectedCohortId] = useState('');
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(false);

  // Create / Edit Exam Modal
  const [showExamModal, setShowExamModal] = useState(false);
  const [editingExam, setEditingExam] = useState(null);
  const [examForm, setExamForm] = useState({
    exam_type: 'Unit Test',
    title: '',
    subject: '',
    max_marks: 25,
    exam_date: new Date().toISOString().split('T')[0],
  });
  const [savingExam, setSavingExam] = useState(false);

  // Manual Marks Entry Modal / Drawer
  const [activeExamRoster, setActiveExamRoster] = useState(null); // Exam object
  const [rosterStudents, setRosterStudents] = useState([]);
  const [marksState, setMarksState] = useState({}); // { [student_id]: { marks: string, absent: bool } }
  const [editReason, setEditReason] = useState('');
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [savingMarks, setSavingMarks] = useState(false);

  // Publish Warning Modal
  const [publishingExam, setPublishingExam] = useState(null);
  const [publishWarnings, setPublishWarnings] = useState([]);
  const [publishingLoading, setPublishingLoading] = useState(false);

  // Excel Upload Modal
  const [excelExam, setExcelExam] = useState(null);
  const [excelFile, setExcelFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirmingBulk, setConfirmingBulk] = useState(false);
  const [bulkReason, setBulkReason] = useState('');

  // Auto-select first cohort
  useEffect(() => {
    if (cohorts.length > 0 && !selectedCohortId) {
      setSelectedCohortId(cohorts[0].id);
    }
  }, [cohorts, selectedCohortId]);

  // Load exams when cohort changes
  useEffect(() => {
    if (selectedCohortId) {
      loadExams(selectedCohortId);
    } else {
      setExams([]);
    }
  }, [selectedCohortId]);

  async function loadExams(cohortId) {
    setLoading(true);
    try {
      const res = await classMarksAPI.listCohortExams(cohortId);
      setExams(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load exams');
    } finally {
      setLoading(false);
    }
  }

  function openCreateExam() {
    setEditingExam(null);
    setExamForm({
      exam_type: 'Unit Test',
      title: '',
      subject: '',
      max_marks: 25,
      exam_date: new Date().toISOString().split('T')[0],
    });
    setShowExamModal(true);
  }

  function openEditExam(exam) {
    setEditingExam(exam);
    setExamForm({
      exam_type: exam.exam_type,
      title: exam.title,
      subject: exam.subject,
      max_marks: Number(exam.max_marks),
      exam_date: exam.exam_date || '',
    });
    setShowExamModal(true);
  }

  async function handleExamSubmit(e) {
    e.preventDefault();
    if (!examForm.title.trim() || !examForm.subject.trim()) {
      toast.error('Title and Subject are required');
      return;
    }
    if (Number(examForm.max_marks) <= 0) {
      toast.error('Max marks must be greater than 0');
      return;
    }

    setSavingExam(true);
    try {
      if (editingExam) {
        await classMarksAPI.updateExam(editingExam.id, {
          title: examForm.title.trim(),
          exam_type: examForm.exam_type.trim(),
          subject: examForm.subject.trim(),
          max_marks: Number(examForm.max_marks),
          exam_date: examForm.exam_date || null,
        });
        toast.success('Exam updated successfully');
      } else {
        await classMarksAPI.createExam({
          cohort_id: selectedCohortId,
          title: examForm.title.trim(),
          exam_type: examForm.exam_type.trim(),
          subject: examForm.subject.trim(),
          max_marks: Number(examForm.max_marks),
          exam_date: examForm.exam_date || null,
        });
        toast.success('Exam created as draft');
      }
      setShowExamModal(false);
      loadExams(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save exam');
    } finally {
      setSavingExam(false);
    }
  }

  async function handleDeleteExam(exam) {
    if (exam.status === 'published') {
      toast.error('Published exams cannot be deleted. Unpublish it first.');
      return;
    }
    if (!window.confirm(`Are you sure you want to delete draft exam "${exam.title}"?`)) {
      return;
    }
    try {
      await classMarksAPI.deleteExam(exam.id);
      toast.success('Draft exam deleted');
      loadExams(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete exam');
    }
  }

  async function handlePublishClick(exam) {
    setPublishingExam(exam);
    setPublishingLoading(true);
    try {
      const res = await classMarksAPI.publishExam(exam.id);
      if (res.data.warnings && res.data.warnings.length > 0) {
        setPublishWarnings(res.data.warnings);
      } else {
        toast.success('Exam published! Marks are now visible to students.');
        setPublishingExam(null);
      }
      loadExams(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to publish exam');
      setPublishingExam(null);
    } finally {
      setPublishingLoading(false);
    }
  }

  async function handleUnpublish(exam) {
    if (!window.confirm(`Unpublish "${exam.title}"? Students will no longer see these marks.`)) {
      return;
    }
    try {
      await classMarksAPI.unpublishExam(exam.id);
      toast.success('Exam unpublished and hidden from students.');
      loadExams(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to unpublish exam');
    }
  }

  // ── Manual Marks Roster ──────────────────────────────────────────
  async function openMarksRoster(exam) {
    setActiveExamRoster(exam);
    setLoadingRoster(true);
    setEditReason('');
    try {
      const res = await classMarksAPI.getRosterMarks(exam.id);
      setRosterStudents(res.data.students);
      const stateMap = {};
      res.data.students.forEach((s) => {
        stateMap[s.student_id] = {
          marks: s.marks_obtained !== null && s.marks_obtained !== undefined ? String(s.marks_obtained) : '',
          absent: Boolean(s.is_absent),
        };
      });
      setMarksState(stateMap);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load class roster');
    } finally {
      setLoadingRoster(false);
    }
  }

  function handleMarkChange(studentId, val) {
    setMarksState((prev) => ({
      ...prev,
      [studentId]: {
        ...prev[studentId],
        marks: val,
        absent: false,
      },
    }));
  }

  function handleAbsentToggle(studentId) {
    setMarksState((prev) => {
      const cur = prev[studentId] || { marks: '', absent: false };
      const nextAbsent = !cur.absent;
      return {
        ...prev,
        [studentId]: {
          marks: nextAbsent ? '' : cur.marks,
          absent: nextAbsent,
        },
      };
    });
  }

  async function handleSaveMarks() {
    if (!activeExamRoster) return;

    if (activeExamRoster.status === 'published' && !editReason.trim()) {
      toast.error('An audit reason is required when editing marks for a published exam.');
      return;
    }

    setSavingMarks(true);
    try {
      const payloadMarks = rosterStudents.map((st) => {
        const item = marksState[st.student_id] || { marks: '', absent: false };
        let marksVal = null;
        if (!item.absent && item.marks !== '') {
          marksVal = Number(item.marks);
        }
        return {
          student_id: st.student_id,
          marks_obtained: marksVal,
          is_absent: Boolean(item.absent),
        };
      });

      await classMarksAPI.saveMarks(activeExamRoster.id, {
        marks: payloadMarks,
        reason: editReason.trim() || null,
      });

      toast.success('Marks saved successfully!');
      setActiveExamRoster(null);
      loadExams(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save marks');
    } finally {
      setSavingMarks(false);
    }
  }

  // ── Excel Workflow ──────────────────────────────────────────────
  function openExcelModal(exam) {
    setExcelExam(exam);
    setExcelFile(null);
    setPreviewData(null);
    setBulkReason('');
  }

  async function handleDownloadTemplate(exam) {
    try {
      const res = await classMarksAPI.downloadTemplate(exam.id);
      const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `marks_template_${exam.title.replace(/\s+/g, '_')}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Template downloaded');
    } catch (err) {
      toast.error('Failed to download template');
    }
  }

  async function handlePreviewUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.xlsx')) {
      toast.error('Only .xlsx spreadsheet files are accepted');
      return;
    }
    setExcelFile(file);
    setPreviewLoading(true);
    try {
      const res = await classMarksAPI.previewUpload(excelExam.id, file);
      setPreviewData(res.data);
      if (res.data.invalid_rows_count > 0) {
        toast((t) => (
          <span className="flex items-center gap-2 text-xs">
            <AlertTriangle className="text-amber-400" size={16} />
            Found {res.data.invalid_rows_count} issue(s) in sheet. Review below.
          </span>
        ));
      } else {
        toast.success(`All ${res.data.valid_rows_count} rows valid and ready to confirm!`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to parse Excel file');
      setExcelFile(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleDownloadErrorReport() {
    if (!previewData?.invalid_rows) return;
    try {
      const res = await classMarksAPI.downloadErrorReport(excelExam.id, previewData.invalid_rows);
      const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `marks_error_report_${excelExam.title.replace(/\s+/g, '_')}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Error report downloaded');
    } catch (err) {
      toast.error('Failed to download error report');
    }
  }

  async function handleConfirmBulkUpload() {
    if (!previewData?.valid_rows || previewData.valid_rows.length === 0) {
      toast.error('No valid rows to save');
      return;
    }
    if (excelExam.status === 'published' && !bulkReason.trim()) {
      toast.error('An audit reason is required when modifying marks for a published exam.');
      return;
    }

    setConfirmingBulk(true);
    try {
      const rowsPayload = previewData.valid_rows.map((r) => ({
        student_id: r.student_id,
        marks_obtained: r.marks_obtained !== null && r.marks_obtained !== undefined ? Number(r.marks_obtained) : null,
        is_absent: Boolean(r.is_absent),
      }));

      await classMarksAPI.confirmUpload(excelExam.id, {
        rows: rowsPayload,
        reason: bulkReason.trim() || null,
      });

      toast.success(`Successfully saved marks for ${rowsPayload.length} students!`);
      setExcelExam(null);
      loadExams(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to confirm marks upload');
    } finally {
      setConfirmingBulk(false);
    }
  }

  const selectedCohort = cohorts.find((c) => c.id === selectedCohortId);

  return (
    <div className="space-y-6">
      {/* Top Bar: Class Selector & Add Exam Button */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/60 border border-white/10 p-4 rounded-2xl backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <Award size={20} />
          </div>
          <div>
            <h2 className="text-white font-bold text-sm">Class Marks &amp; Examinations</h2>
            <p className="text-xs text-slate-400">Manage exams, manual grade entries, and Excel bulk sheets.</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Cohort Selector */}
          <select
            value={selectedCohortId}
            onChange={(e) => setSelectedCohortId(e.target.value)}
            className="bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-xs font-semibold text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            {cohorts.map((c) => (
              <option key={c.id} value={c.id} className="bg-slate-900 text-slate-200">
                {c.name} ({c.academic_year})
              </option>
            ))}
          </select>

          <button
            onClick={openCreateExam}
            disabled={!selectedCohortId}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl flex items-center gap-1.5 shadow-lg shadow-emerald-500/20 transition-all whitespace-nowrap"
          >
            <Plus size={15} /> Add Exam
          </button>
        </div>
      </div>

      {/* Main Exams List */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 text-sm">
          <RefreshCw className="animate-spin inline-block mr-2" size={16} /> Loading exams...
        </div>
      ) : exams.length === 0 ? (
        <div className="p-12 rounded-2xl bg-slate-900/40 border border-white/5 text-center">
          <Award size={36} className="mx-auto text-slate-600 mb-3" />
          <p className="text-slate-300 font-medium text-sm">No exams created yet for {selectedCohort?.name}</p>
          <p className="text-slate-500 text-xs mt-1">Create an exam to enter marks by hand or via Excel.</p>
          <button
            onClick={openCreateExam}
            className="mt-4 px-4 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-semibold rounded-xl transition-all"
          >
            + Create First Exam
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {exams.map((ex) => (
            <div
              key={ex.id}
              className="bg-slate-900/50 border border-white/10 hover:border-white/20 rounded-2xl p-5 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-white font-bold text-base">{ex.title}</span>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-white/5 border border-white/10 text-slate-300">
                    {ex.subject}
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
                    {ex.exam_type}
                  </span>
                  {ex.status === 'published' ? (
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500 text-black flex items-center gap-1">
                      <CheckCircle2 size={12} /> Published
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      Draft
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
                  <span>Max Marks: <strong className="text-slate-200">{ex.max_marks}</strong></span>
                  {ex.exam_date && <span>Date: <strong className="text-slate-200">{ex.exam_date}</strong></span>}
                  <span className="text-slate-500">|</span>
                  <span className="text-emerald-400 font-medium">{ex.graded_count} Graded</span>
                  <span className="text-rose-400 font-medium">{ex.absent_count} Absent</span>
                  <span className="text-slate-400 font-medium">{ex.unentered_count} Unentered</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => openMarksRoster(ex)}
                  className="px-3 py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-400 text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-all"
                >
                  <Edit2 size={13} /> Enter Marks
                </button>

                <button
                  onClick={() => openExcelModal(ex)}
                  className="px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-slate-200 text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-all"
                >
                  <FileSpreadsheet size={13} /> Excel Sheet
                </button>

                {ex.status === 'published' ? (
                  <button
                    onClick={() => handleUnpublish(ex)}
                    className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 text-xs font-semibold rounded-xl transition-all"
                  >
                    Unpublish
                  </button>
                ) : (
                  <button
                    onClick={() => handlePublishClick(ex)}
                    className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/10 transition-all flex items-center gap-1"
                  >
                    <CheckCircle2 size={13} /> Publish
                  </button>
                )}

                <button
                  onClick={() => openEditExam(ex)}
                  className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition-all"
                  title="Edit exam metadata"
                >
                  <Edit2 size={15} />
                </button>

                {ex.status !== 'published' && (
                  <button
                    onClick={() => handleDeleteExam(ex)}
                    className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-rose-500/10 transition-all"
                    title="Delete draft exam"
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          MODAL 1: CREATE / EDIT EXAM
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showExamModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl relative"
            >
              <button
                onClick={() => setShowExamModal(false)}
                className="absolute top-5 right-5 text-slate-400 hover:text-white transition-colors"
              >
                <X size={18} />
              </button>

              <h3 className="text-lg font-bold text-white mb-1">
                {editingExam ? 'Edit Exam' : 'Create New Exam'}
              </h3>
              <p className="text-xs text-slate-400 mb-5">
                {editingExam ? 'Update exam parameters. Max marks cannot be lowered below existing student marks.' : 'Create a draft exam for this class cohort.'}
              </p>

              <form onSubmit={handleExamSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Exam Type</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Unit Test, Internals, Mid-term"
                    value={examForm.exam_type}
                    onChange={(e) => setExamForm({ ...examForm, exam_type: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Exam Title</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Unit Test 1"
                    value={examForm.title}
                    onChange={(e) => setExamForm({ ...examForm, title: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Subject</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Mathematics, Physics"
                    value={examForm.subject}
                    onChange={(e) => setExamForm({ ...examForm, subject: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Max Marks</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={examForm.max_marks}
                      onChange={(e) => setExamForm({ ...examForm, max_marks: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase mb-1">Exam Date</label>
                    <input
                      type="date"
                      value={examForm.exam_date}
                      onChange={(e) => setExamForm({ ...examForm, exam_date: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 font-mono"
                    />
                  </div>
                </div>

                <div className="pt-3 flex items-center justify-end gap-3 border-t border-white/10">
                  <button
                    type="button"
                    onClick={() => setShowExamModal(false)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={savingExam}
                    className="px-5 py-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/20"
                  >
                    {savingExam ? 'Saving...' : editingExam ? 'Update Exam' : 'Create Draft'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL 2: MANUAL MARKS ENTRY
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {activeExamRoster && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              className="w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-white/10 rounded-2xl flex flex-col shadow-2xl overflow-hidden"
            >
              {/* Header */}
              <div className="p-5 border-b border-white/10 flex items-center justify-between bg-black/30">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-white font-bold text-base">{activeExamRoster.title}</h3>
                    <span className="text-xs px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300">
                      {activeExamRoster.subject}
                    </span>
                    <span className="text-xs text-emerald-400 font-mono font-bold">
                      Max: {activeExamRoster.max_marks}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Enter marks or mark as Absent. Students with no marks entered will see &ldquo;Not entered yet&rdquo;.
                  </p>
                </div>
                <button
                  onClick={() => setActiveExamRoster(null)}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/5"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Published Audit Warning Banner */}
              {activeExamRoster.status === 'published' && (
                <div className="p-4 bg-amber-500/10 border-b border-amber-500/20 text-amber-300 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <ShieldAlert size={16} className="text-amber-400 flex-shrink-0" />
                    <span>
                      <strong>Audit Notice:</strong> This exam is currently published. Any modifications will be recorded in the change log.
                    </span>
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <label className="text-[11px] font-bold uppercase tracking-wider text-amber-400 whitespace-nowrap">
                      Reason:
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Recount of Question 2"
                      value={editReason}
                      onChange={(e) => setEditReason(e.target.value)}
                      className="bg-black/40 border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-amber-300/40 focus:outline-none focus:border-amber-400 w-full sm:w-64"
                    />
                  </div>
                </div>
              )}

              {/* Table Body */}
              <div className="flex-1 overflow-y-auto p-4">
                {loadingRoster ? (
                  <div className="p-12 text-center text-slate-500 text-sm">
                    <RefreshCw className="animate-spin inline mr-2" size={16} /> Loading student roster...
                  </div>
                ) : rosterStudents.length === 0 ? (
                  <div className="p-8 text-center text-slate-400 text-sm">No active students in this cohort.</div>
                ) : (
                  <div className="rounded-xl border border-white/10 overflow-hidden bg-black/20">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-800/60 border-b border-white/10 text-slate-400 uppercase font-semibold">
                        <tr>
                          <th className="py-2.5 px-4">#</th>
                          <th className="py-2.5 px-4">Student Name</th>
                          <th className="py-2.5 px-4">Identifier</th>
                          <th className="py-2.5 px-4 text-center">Marks (0 - {activeExamRoster.max_marks})</th>
                          <th className="py-2.5 px-4 text-center">Absent</th>
                          <th className="py-2.5 px-4 text-right">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {rosterStudents.map((st, idx) => {
                          const item = marksState[st.student_id] || { marks: '', absent: false };
                          return (
                            <tr key={st.student_id} className="hover:bg-white/[0.02] transition-colors">
                              <td className="py-3 px-4 text-slate-500 font-mono">{idx + 1}</td>
                              <td className="py-3 px-4 font-semibold text-white">
                                {st.student_name || st.student_username || 'Student'}
                              </td>
                              <td className="py-3 px-4 text-slate-400 font-mono">
                                {st.student_email || st.student_username}
                              </td>
                              <td className="py-3 px-4 text-center">
                                <input
                                  type="number"
                                  step="0.01"
                                  min="0"
                                  max={activeExamRoster.max_marks}
                                  placeholder="Leave blank"
                                  disabled={item.absent}
                                  value={item.marks}
                                  onChange={(e) => handleMarkChange(st.student_id, e.target.value)}
                                  className={`w-28 text-center bg-black/40 border border-white/10 rounded-lg px-2.5 py-1.5 font-mono text-white focus:outline-none focus:border-emerald-500 ${
                                    item.absent ? 'opacity-30 cursor-not-allowed bg-slate-950' : ''
                                  }`}
                                />
                              </td>
                              <td className="py-3 px-4 text-center">
                                <button
                                  type="button"
                                  onClick={() => handleAbsentToggle(st.student_id)}
                                  className={`px-3 py-1 rounded-lg font-semibold text-xs transition-all ${
                                    item.absent
                                      ? 'bg-rose-500 text-white shadow-lg shadow-rose-500/20'
                                      : 'bg-white/5 text-slate-400 hover:text-white'
                                  }`}
                                >
                                  {item.absent ? 'Absent' : 'Present'}
                                </button>
                              </td>
                              <td className="py-3 px-4 text-right">
                                {item.absent ? (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                    Absent
                                  </span>
                                ) : item.marks !== '' ? (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                    Graded
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-700/40 text-slate-400">
                                    Not entered
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-white/10 bg-black/30 flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  {rosterStudents.length} active student{rosterStudents.length === 1 ? '' : 's'} in class
                </span>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setActiveExamRoster(null)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveMarks}
                    disabled={savingMarks}
                    className="px-5 py-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/20 flex items-center gap-1.5"
                  >
                    {savingMarks ? (
                      <RefreshCw size={14} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={14} />
                    )}
                    {savingMarks ? 'Saving...' : 'Save Marks'}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL 3: PUBLISH WARNING CONFIRMATION
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {publishingExam && publishWarnings.length > 0 && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md bg-slate-900 border border-amber-500/30 rounded-2xl p-6 shadow-2xl relative"
            >
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 mb-4">
                <AlertTriangle size={24} />
              </div>
              <h3 className="text-lg font-bold text-white mb-2">Notice for &ldquo;{publishingExam.title}&rdquo;</h3>
              <div className="space-y-2 mb-6">
                {publishWarnings.map((w, idx) => (
                  <p key={idx} className="text-xs text-amber-300/90 leading-relaxed bg-amber-500/10 p-3 rounded-xl border border-amber-500/20">
                    {w}
                  </p>
                ))}
                <p className="text-xs text-slate-400 mt-2">
                  The exam is now published. Students with missing marks will simply see &ldquo;Not entered yet&rdquo; until you enter them.
                </p>
              </div>
              <button
                onClick={() => setPublishingExam(null)}
                className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs rounded-xl transition-all"
              >
                Understood
              </button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL 4: EXCEL WORKFLOW (PREVIEW & CONFIRM)
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {excelExam && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              className="w-full max-w-3xl max-h-[90vh] bg-slate-900 border border-white/10 rounded-2xl flex flex-col shadow-2xl overflow-hidden"
            >
              {/* Header */}
              <div className="p-5 border-b border-white/10 flex items-center justify-between bg-black/30">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                    <FileSpreadsheet size={18} />
                  </div>
                  <div>
                    <h3 className="text-white font-bold text-sm">Excel Marks Entry — {excelExam.title}</h3>
                    <p className="text-xs text-slate-400">Download prefilled template, edit marks, and upload with safety preview.</p>
                  </div>
                </div>
                <button
                  onClick={() => setExcelExam(null)}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/5"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Upload & Preview Step */}
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                {/* 1. Download Template Box */}
                <div className="p-4 rounded-xl bg-slate-950/60 border border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">Step 1: Download Template</h4>
                    <p className="text-xs text-slate-400">Pre-populated with active students from {selectedCohort?.name}.</p>
                  </div>
                  <button
                    onClick={() => handleDownloadTemplate(excelExam)}
                    className="px-3.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-emerald-400 text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-all self-start sm:self-auto"
                  >
                    <Download size={14} /> Download .xlsx
                  </button>
                </div>

                {/* 2. File Upload Box */}
                <div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-2">Step 2: Upload Completed Sheet</h4>
                  <label className="border-2 border-dashed border-white/10 hover:border-emerald-500/40 rounded-2xl p-6 flex flex-col items-center justify-center cursor-pointer transition-colors bg-black/20">
                    <Upload size={24} className="text-emerald-400 mb-2" />
                    <span className="text-xs font-semibold text-white">Click to select .xlsx file</span>
                    <span className="text-[11px] text-slate-500 mt-0.5">Maximum size 2 MB, up to 500 rows</span>
                    <input
                      type="file"
                      accept=".xlsx"
                      onChange={handlePreviewUpload}
                      className="hidden"
                    />
                  </label>
                </div>

                {previewLoading && (
                  <div className="p-8 text-center text-slate-500 text-xs">
                    <RefreshCw className="animate-spin inline mr-2" size={15} /> Validating sheet on server...
                  </div>
                )}

                {/* 3. Preview Results */}
                {previewData && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">Step 3: Server Preview</span>
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          {previewData.valid_rows_count} Valid
                        </span>
                        {previewData.invalid_rows_count > 0 && (
                          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                            {previewData.invalid_rows_count} Rejected
                          </span>
                        )}
                      </div>
                      {previewData.invalid_rows_count > 0 && (
                        <button
                          onClick={handleDownloadErrorReport}
                          className="px-3 py-1 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-300 text-xs font-semibold rounded-xl flex items-center gap-1 transition-all"
                        >
                          <Download size={13} /> Error Report
                        </button>
                      )}
                    </div>

                    {/* Preview Table */}
                    <div className="rounded-xl border border-white/10 overflow-hidden max-h-60 overflow-y-auto bg-black/20">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-800/60 border-b border-white/10 text-slate-400 uppercase font-semibold">
                          <tr>
                            <th className="py-2 px-3">Row</th>
                            <th className="py-2 px-3">Identifier</th>
                            <th className="py-2 px-3">Marks</th>
                            <th className="py-2 px-3">Absent</th>
                            <th className="py-2 px-3">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 font-mono">
                          {previewData.valid_rows.map((r, i) => (
                            <tr key={`v-${i}`} className="text-slate-300">
                              <td className="py-1.5 px-3 text-slate-500">{r.row_num}</td>
                              <td className="py-1.5 px-3">{r.student_name || r.student_identifier}</td>
                              <td className="py-1.5 px-3 text-emerald-400">{r.marks_obtained !== null ? r.marks_obtained : '-'}</td>
                              <td className="py-1.5 px-3">{r.is_absent ? 'YES' : 'NO'}</td>
                              <td className="py-1.5 px-3 text-emerald-400 font-bold">Valid</td>
                            </tr>
                          ))}
                          {previewData.invalid_rows.map((r, i) => (
                            <tr key={`inv-${i}`} className="bg-rose-500/5 text-rose-300">
                              <td className="py-1.5 px-3 text-slate-500">{r.row_num}</td>
                              <td className="py-1.5 px-3">{r.student_identifier}</td>
                              <td className="py-1.5 px-3">{r.marks_obtained || '-'}</td>
                              <td className="py-1.5 px-3">{r.is_absent ? 'YES' : 'NO'}</td>
                              <td className="py-1.5 px-3 text-rose-400">{r.error_reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Audit Reason if Published */}
                    {excelExam.status === 'published' && (
                      <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl space-y-1">
                        <label className="text-[11px] font-bold text-amber-400 uppercase">
                          Reason for modifying published marks:
                        </label>
                        <input
                          type="text"
                          required
                          placeholder="e.g. Bulk re-grading of test submissions"
                          value={bulkReason}
                          onChange={(e) => setBulkReason(e.target.value)}
                          className="w-full bg-black/40 border border-amber-500/30 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-amber-400"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-white/10 bg-black/30 flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  {previewData ? `${previewData.valid_rows_count} rows ready to save` : 'Awaiting file upload'}
                </span>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setExcelExam(null)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmBulkUpload}
                    disabled={!previewData || previewData.valid_rows_count === 0 || confirmingBulk}
                    className="px-5 py-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/20 flex items-center gap-1.5"
                  >
                    {confirmingBulk ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                    {confirmingBulk ? 'Saving...' : 'Confirm & Save Marks'}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
