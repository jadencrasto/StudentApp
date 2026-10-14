import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Calendar, Upload, Sparkles, Plus, Trash2, CheckCircle2, AlertCircle,
  Clock, ShieldAlert, RefreshCw, FileText, Check, ChevronDown, Eye, Edit3,
  Layers, AlertTriangle
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { classTimetableAPI } from '../../api/client';

const DAYS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
];

export default function AdminTimetableTab({ cohorts, institution }) {
  const [selectedCohortId, setSelectedCohortId] = useState('');
  const [overview, setOverview] = useState(null);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [suggestedSubjects, setSuggestedSubjects] = useState([]);

  // Draft state
  const [draftEntries, setDraftEntries] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [savingDraft, setSavingDraft] = useState(false);
  const [discardingDraft, setDiscardingDraft] = useState(false);
  const [publishing, setPublishing] = useState(false);

  // Upload & Extraction state
  const [uploadFile, setUploadFile] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [showReplaceModal, setShowReplaceModal] = useState(false);
  const [showForcePublishModal, setShowForcePublishModal] = useState(false);
  const [remainingAttempts, setRemainingAttempts] = useState(5);

  // Active view for published timetable preview
  const [showPublishedPreview, setShowPublishedPreview] = useState(false);

  // Auto-select first cohort if none selected
  useEffect(() => {
    if (cohorts.length > 0 && !selectedCohortId) {
      setSelectedCohortId(cohorts[0].id);
    }
  }, [cohorts, selectedCohortId]);

  // Load overview whenever selected cohort changes
  useEffect(() => {
    if (selectedCohortId) {
      loadCohortTimetable(selectedCohortId);
    } else {
      setOverview(null);
      setDraftEntries([]);
      setWarnings([]);
    }
  }, [selectedCohortId]);

  async function loadCohortTimetable(cohortId) {
    setLoadingOverview(true);
    try {
      const [overviewRes, subjectsRes] = await Promise.all([
        classTimetableAPI.getOverview(cohortId),
        classTimetableAPI.getSuggestedSubjects(cohortId).catch(() => ({ data: [] })),
      ]);
      setOverview(overviewRes.data);
      setSuggestedSubjects(subjectsRes.data || []);

      if (overviewRes.data.has_draft && overviewRes.data.draft) {
        setDraftEntries(overviewRes.data.draft.entries || []);
      } else {
        setDraftEntries([]);
      }
      setWarnings([]);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load class timetable');
    } finally {
      setLoadingOverview(false);
    }
  }

  // ── Extraction Handler ──────────────────────────────────────────
  async function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    // Check file type
    const validTypes = ['image/jpeg', 'image/png', 'image/jpg'];
    if (!validTypes.includes(file.type)) {
      toast.error('Only JPG and PNG image files are supported.');
      return;
    }
    // Check file size (10MB)
    if (file.size > 10 * 1024 * 1024) {
      toast.error('Image size exceeds maximum limit of 10MB.');
      return;
    }

    setUploadFile(file);

    // If draft already exists, ask for confirmation
    if (overview?.has_draft) {
      setShowReplaceModal(true);
    } else {
      await executeExtraction(file, false);
    }
  }

  async function executeExtraction(file, replaceDraft) {
    if (!selectedCohortId) {
      toast.error('Please select a class first');
      return;
    }

    setExtracting(true);
    setShowReplaceModal(false);
    try {
      const res = await classTimetableAPI.extractTimetable(selectedCohortId, file, replaceDraft);
      const data = res.data;

      if (data.status === 'success') {
        toast.success(data.message || 'Timetable extracted via Gemini Vision!');
      } else if (data.status === 'fallback_ocr') {
        toast.success(data.message || 'Extracted via OCR fallback.');
      } else {
        toast.error(data.message || 'AI extraction failed. You can enter classes manually.');
      }

      if (data.remaining_attempts !== undefined) {
        setRemainingAttempts(data.remaining_attempts);
      }

      // Refresh overview
      await loadCohortTimetable(selectedCohortId);
    } catch (err) {
      if (err.response?.status === 409) {
        setShowReplaceModal(true);
      } else if (err.response?.status === 429) {
        toast.error(err.response.data.detail || 'Extraction rate limit reached (5/hour).');
      } else {
        toast.error(err.response?.data?.detail || 'Extraction failed');
      }
    } finally {
      setExtracting(false);
      setUploadFile(null);
    }
  }

  // ── Manual Draft Creation ────────────────────────────────────────
  function handleStartManualDraft() {
    setDraftEntries([
      { day_of_week: 0, start_time: '09:00', end_time: '10:00', subject: '', room: '', teacher: '' }
    ]);
    setWarnings([]);
  }

  // ── Draft Row Modifications ──────────────────────────────────────
  function handleAddRow() {
    if (draftEntries.length >= 100) {
      toast.error('Maximum 100 class slots allowed per timetable.');
      return;
    }
    setDraftEntries([
      ...draftEntries,
      { day_of_week: 0, start_time: '09:00', end_time: '10:00', subject: '', room: '', teacher: '' }
    ]);
  }

  function handleUpdateRow(index, field, value) {
    const updated = [...draftEntries];
    updated[index] = { ...updated[index], [field]: value };
    setDraftEntries(updated);
  }

  function handleDeleteRow(index) {
    setDraftEntries(draftEntries.filter((_, i) => i !== index));
  }

  // ── Save Draft ───────────────────────────────────────────────────
  async function handleSaveDraft() {
    if (!selectedCohortId) return;
    setSavingDraft(true);
    try {
      const res = await classTimetableAPI.saveDraft(selectedCohortId, {
        entries: draftEntries.map((e) => ({
          day_of_week: parseInt(e.day_of_week, 10),
          start_time: e.start_time,
          end_time: e.end_time,
          subject: (e.subject || '').trim(),
          room: (e.room || '').trim() || null,
          teacher: (e.teacher || '').trim() || null,
        })),
      });
      setWarnings(res.data.warnings || []);
      toast.success('Draft timetable saved');
      await loadCohortTimetable(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save draft');
    } finally {
      setSavingDraft(false);
    }
  }

  // ── Discard Draft ────────────────────────────────────────────────
  async function handleDiscardDraft() {
    if (!window.confirm('Are you sure you want to discard this draft? Any uploaded image and unsaved changes will be permanently removed.')) {
      return;
    }
    setDiscardingDraft(true);
    try {
      await classTimetableAPI.discardDraft(selectedCohortId);
      toast.success('Draft timetable discarded');
      await loadCohortTimetable(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to discard draft');
    } finally {
      setDiscardingDraft(false);
    }
  }

  // ── Publish Timetable ────────────────────────────────────────────
  async function handlePublish(force = false) {
    if (!selectedCohortId) return;

    // Check basic client validation first
    if (!draftEntries.length) {
      toast.error('Cannot publish an empty timetable. Please add at least one slot.');
      return;
    }

    setPublishing(true);
    setShowForcePublishModal(false);
    try {
      // First save current draft changes if any
      await classTimetableAPI.saveDraft(selectedCohortId, {
        entries: draftEntries.map((e) => ({
          day_of_week: parseInt(e.day_of_week, 10),
          start_time: e.start_time,
          end_time: e.end_time,
          subject: (e.subject || '').trim(),
          room: (e.room || '').trim() || null,
          teacher: (e.teacher || '').trim() || null,
        })),
      });

      const res = await classTimetableAPI.publishTimetable(selectedCohortId, force);
      toast.success('Timetable published successfully! It is now visible to all students in this class.');
      setWarnings([]);
      await loadCohortTimetable(selectedCohortId);
    } catch (err) {
      if (err.response?.status === 422 && err.response?.data?.detail?.can_override) {
        setWarnings(err.response.data.detail.warnings || []);
        setShowForcePublishModal(true);
      } else {
        toast.error(err.response?.data?.detail?.message || err.response?.data?.detail || 'Failed to publish timetable');
      }
    } finally {
      setPublishing(false);
    }
  }

  // ── Edit Published (Copy to Draft) ───────────────────────────────
  async function handleEditPublished() {
    if (!selectedCohortId) return;
    if (overview?.has_draft) {
      toast.error('A draft already exists. Please finish or discard it first.');
      return;
    }
    try {
      await classTimetableAPI.editPublished(selectedCohortId);
      toast.success('Copied published timetable to draft for editing');
      await loadCohortTimetable(selectedCohortId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to edit published timetable');
    }
  }

  const selectedCohort = cohorts.find((c) => c.id === selectedCohortId);

  return (
    <div className="space-y-6">
      {/* Top Header & Class Selector */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-black border border-emerald-500/20 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                <Calendar size={12} /> Class Timetable
              </span>
              <span className="text-xs text-slate-400">Strictly per-class &bull; Read-only for students</span>
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">Class Timetable Management</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Upload timetable photos for AI parsing, review draft schedules, and publish atomically.
            </p>
          </div>

          {/* Class Selector Dropdown */}
          <div className="flex items-center gap-3">
            <div className="relative min-w-[240px]">
              <select
                value={selectedCohortId}
                onChange={(e) => setSelectedCohortId(e.target.value)}
                className="w-full appearance-none px-4 py-2.5 pr-10 rounded-xl bg-black/80 border border-emerald-500/30 text-white text-sm font-medium focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400 transition-colors"
              >
                {cohorts.length === 0 ? (
                  <option value="">No classes found</option>
                ) : (
                  cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.academic_year || 'Current'})
                    </option>
                  ))
                )}
              </select>
              <ChevronDown size={16} className="absolute right-3.5 top-3.5 text-slate-400 pointer-events-none" />
            </div>

            <button
              onClick={() => selectedCohortId && loadCohortTimetable(selectedCohortId)}
              disabled={loadingOverview}
              className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors border border-white/10"
              title="Refresh"
            >
              <RefreshCw size={16} className={loadingOverview ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>
      </div>

      {loadingOverview && (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loadingOverview && selectedCohort && (
        <div className="space-y-6">
          {/* ── Status Banner & Published Overview Card ───────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Published Timetable Status Card */}
            <div className="p-5 rounded-xl bg-black/40 border border-white/10 backdrop-blur-md">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Live Student Schedule
                    </span>
                    {overview?.has_published ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                        <CheckCircle2 size={10} /> Published
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-800 text-slate-400 border border-white/10">
                        None Published
                      </span>
                    )}
                  </div>
                  <h3 className="text-base font-semibold text-white">
                    {selectedCohort.name}
                  </h3>
                  {overview?.has_published ? (
                    <p className="text-xs text-slate-400 mt-1">
                      {overview.published?.entries?.length || 0} class sessions active &bull; Published on{' '}
                      {new Date(overview.published?.published_at).toLocaleDateString()}
                    </p>
                  ) : (
                    <p className="text-xs text-slate-500 mt-1">
                      Students in this class currently have no official timetable published.
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {overview?.has_published && (
                    <>
                      <button
                        onClick={() => setShowPublishedPreview(!showPublishedPreview)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 transition-colors flex items-center gap-1.5"
                      >
                        <Eye size={13} /> {showPublishedPreview ? 'Hide' : 'Preview'}
                      </button>
                      <button
                        onClick={handleEditPublished}
                        disabled={overview.has_draft}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 transition-colors flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
                        title={overview.has_draft ? 'A draft already exists' : 'Copy published timetable to draft'}
                      >
                        <Edit3 size={13} /> Edit Current
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Published Timetable Preview Modal/Collapse */}
              {showPublishedPreview && overview?.published && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <div className="overflow-x-auto max-h-60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-white/5 text-slate-400 uppercase font-semibold">
                        <tr>
                          <th className="p-2">Day</th>
                          <th className="p-2">Time</th>
                          <th className="p-2">Subject</th>
                          <th className="p-2">Room</th>
                          <th className="p-2">Teacher</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5 text-slate-300">
                        {overview.published.entries.map((item, idx) => (
                          <tr key={idx} className="hover:bg-white/5">
                            <td className="p-2 font-medium text-emerald-400">{DAYS[item.day_of_week]?.label || item.day_of_week}</td>
                            <td className="p-2 font-mono">{item.start_time} - {item.end_time}</td>
                            <td className="p-2 font-semibold text-white">{item.subject}</td>
                            <td className="p-2 text-slate-400">{item.room || '—'}</td>
                            <td className="p-2 text-slate-400">{item.teacher || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* AI Extraction Rate Limit & Server Policy Card */}
            <div className="p-5 rounded-xl bg-black/40 border border-white/10 backdrop-blur-md flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Server AI Extraction Quota
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {remainingAttempts} / 5 attempts remaining
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white">Gemini Vision with Tesseract OCR</h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  Extracts timetable images into editable drafts without overwriting published schedules.
                  Images are re-encoded, dimension-bounded (&le;8000px), and automatically deleted once published or discarded.
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between text-[11px] text-slate-500">
                <span>Uploads folder: git-ignored &amp; secured</span>
                <span>Server Rate Limit: 5/hr</span>
              </div>
            </div>
          </div>

          {/* ── Overlap Warnings Alert ─────────────────────────────────── */}
          {warnings.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-3"
            >
              <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold text-amber-200">Overlapping class slots detected:</p>
                <ul className="mt-1 list-disc list-inside space-y-0.5 text-amber-300/90">
                  {warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
                <p className="mt-1.5 text-amber-400 text-[11px]">
                  You can edit the time slots below, or choose to publish anyway if intentional.
                </p>
              </div>
            </motion.div>
          )}

          {/* ── Main Work Area: Upload / Draft Editor ───────────────────── */}
          {(!overview?.has_draft && draftEntries.length === 0) ? (
            /* No draft exists: Show Upload or Start from Scratch */
            <div className="p-8 rounded-2xl bg-black/40 border border-white/10 backdrop-blur-xl text-center">
              <div className="max-w-md mx-auto space-y-4">
                <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto shadow-lg shadow-emerald-500/10">
                  <Sparkles size={28} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white">Create Timetable for {selectedCohort.name}</h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Upload a timetable photo or screenshot to parse automatically, or enter the schedule by hand.
                  </p>
                </div>

                <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
                  <label className="relative flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-black font-semibold text-sm transition-all shadow-lg shadow-emerald-500/20 cursor-pointer">
                    <Upload size={16} />
                    <span>{extracting ? 'Extracting schedule...' : 'Upload Timetable Image'}</span>
                    <input
                      type="file"
                      accept=".png,.jpg,.jpeg"
                      onChange={handleFileSelect}
                      disabled={extracting}
                      className="hidden"
                    />
                  </label>

                  <button
                    onClick={handleStartManualDraft}
                    className="px-5 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white font-semibold text-sm border border-white/10 transition-colors"
                  >
                    Start from Scratch (Manual Entry)
                  </button>
                </div>

                <p className="text-[11px] text-slate-500">
                  Supported: JPG, PNG &bull; Max 10MB &bull; Draft is created safely in private review mode
                </p>
              </div>
            </div>
          ) : (
            /* Draft in Progress: Editable Grid Review Screen */
            <div className="p-6 rounded-2xl bg-black/60 border border-emerald-500/30 backdrop-blur-xl space-y-6 shadow-2xl shadow-emerald-950/20">
              {/* Draft Header Toolbar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/10">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1">
                      <Clock size={11} /> Draft Timetable
                    </span>
                    <span className="text-xs text-slate-400">
                      {draftEntries.length} / 100 slots &bull; Hidden from students
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-white mt-1">Review &amp; Edit Timetable</h3>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  {/* Upload new photo trigger */}
                  <label className="px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 text-xs font-semibold cursor-pointer transition-colors flex items-center gap-1.5">
                    <Upload size={14} />
                    <span>Replace Image</span>
                    <input
                      type="file"
                      accept=".png,.jpg,.jpeg"
                      onChange={handleFileSelect}
                      disabled={extracting}
                      className="hidden"
                    />
                  </label>

                  {/* Discard Draft */}
                  <button
                    onClick={handleDiscardDraft}
                    disabled={discardingDraft}
                    className="px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-semibold transition-colors flex items-center gap-1.5"
                  >
                    <Trash2 size={14} /> Discard Draft
                  </button>

                  {/* Save Draft */}
                  <button
                    onClick={handleSaveDraft}
                    disabled={savingDraft}
                    className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white border border-white/20 text-xs font-semibold transition-colors flex items-center gap-1.5"
                  >
                    <Check size={14} /> {savingDraft ? 'Saving...' : 'Save Draft'}
                  </button>

                  {/* Publish Timetable */}
                  <button
                    onClick={() => handlePublish(false)}
                    disabled={publishing || !draftEntries.length}
                    className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-black font-bold text-xs transition-all shadow-lg shadow-emerald-500/25 flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <CheckCircle2 size={15} /> {publishing ? 'Publishing...' : 'Publish Timetable'}
                  </button>
                </div>
              </div>

              {/* Editable Slots Table */}
              <div className="overflow-x-auto rounded-xl border border-white/10">
                <table className="w-full text-left text-xs">
                  <thead className="bg-white/5 text-slate-400 uppercase font-semibold">
                    <tr>
                      <th className="p-3 w-10 text-center">#</th>
                      <th className="p-3 w-36">Day of Week</th>
                      <th className="p-3 w-32">Start Time</th>
                      <th className="p-3 w-32">End Time</th>
                      <th className="p-3">Subject Name *</th>
                      <th className="p-3 w-36">Room / Lab</th>
                      <th className="p-3 w-40">Teacher / Instructor</th>
                      <th className="p-3 w-16 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {draftEntries.map((row, idx) => (
                      <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                        <td className="p-3 text-center text-slate-500 font-mono">{idx + 1}</td>
                        <td className="p-3">
                          <select
                            value={row.day_of_week}
                            onChange={(e) => handleUpdateRow(idx, 'day_of_week', parseInt(e.target.value, 10))}
                            className="w-full px-2.5 py-1.5 rounded-lg bg-black/60 border border-white/15 text-emerald-400 font-medium text-xs focus:outline-none focus:border-emerald-400"
                          >
                            {DAYS.map((d) => (
                              <option key={d.value} value={d.value}>
                                {d.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="p-3">
                          <input
                            type="time"
                            value={row.start_time}
                            onChange={(e) => handleUpdateRow(idx, 'start_time', e.target.value)}
                            className="w-full px-2.5 py-1.5 rounded-lg bg-black/60 border border-white/15 text-white font-mono text-xs focus:outline-none focus:border-emerald-400"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="time"
                            value={row.end_time}
                            onChange={(e) => handleUpdateRow(idx, 'end_time', e.target.value)}
                            className="w-full px-2.5 py-1.5 rounded-lg bg-black/60 border border-white/15 text-white font-mono text-xs focus:outline-none focus:border-emerald-400"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            list="suggested-subjects-list"
                            value={row.subject}
                            maxLength={100}
                            placeholder="e.g. Mathematics, Physics"
                            onChange={(e) => handleUpdateRow(idx, 'subject', e.target.value)}
                            className="w-full px-3 py-1.5 rounded-lg bg-black/60 border border-white/15 text-white font-semibold text-xs placeholder:text-slate-600 focus:outline-none focus:border-emerald-400"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.room || ''}
                            maxLength={50}
                            placeholder="Room 101"
                            onChange={(e) => handleUpdateRow(idx, 'room', e.target.value)}
                            className="w-full px-2.5 py-1.5 rounded-lg bg-black/60 border border-white/15 text-slate-300 text-xs placeholder:text-slate-600 focus:outline-none focus:border-emerald-400"
                          />
                        </td>
                        <td className="p-3">
                          <input
                            type="text"
                            value={row.teacher || ''}
                            maxLength={100}
                            placeholder="Dr. Smith"
                            onChange={(e) => handleUpdateRow(idx, 'teacher', e.target.value)}
                            className="w-full px-2.5 py-1.5 rounded-lg bg-black/60 border border-white/15 text-slate-300 text-xs placeholder:text-slate-600 focus:outline-none focus:border-emerald-400"
                          />
                        </td>
                        <td className="p-3 text-center">
                          <button
                            onClick={() => handleDeleteRow(idx)}
                            className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 transition-colors"
                            title="Delete row"
                          >
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Suggested Subjects Datalist */}
              <datalist id="suggested-subjects-list">
                {suggestedSubjects.map((s, idx) => (
                  <option key={idx} value={s} />
                ))}
              </datalist>

              {/* Add Row Button & Summary */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={handleAddRow}
                  disabled={draftEntries.length >= 100}
                  className="px-4 py-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-40"
                >
                  <Plus size={14} /> Add Class Slot
                </button>

                <p className="text-[11px] text-slate-400">
                  Total slots: <span className="font-bold text-white">{draftEntries.length}</span> (capped at 100)
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Replace Existing Draft Confirmation Modal ─────────────── */}
      <AnimatePresence>
        {showReplaceModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 rounded-2xl bg-slate-900 border border-emerald-500/30 shadow-2xl space-y-4"
            >
              <div className="flex items-center gap-3 text-amber-400">
                <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20">
                  <AlertTriangle size={24} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Draft Timetable Exists</h3>
                  <p className="text-xs text-slate-400">Replace current draft with new AI extraction?</p>
                </div>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed">
                A draft timetable already exists for this class. Uploading a new image will replace the current draft and discard unsaved modifications.
              </p>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => {
                    setShowReplaceModal(false);
                    setUploadFile(null);
                  }}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white bg-white/5 hover:bg-white/10 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => executeExtraction(uploadFile, true)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-black bg-emerald-400 hover:bg-emerald-300 transition-colors shadow-lg shadow-emerald-500/20"
                >
                  Yes, Replace Draft
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── Overlap Force Publish Confirmation Modal ──────────────── */}
      <AnimatePresence>
        {showForcePublishModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-lg p-6 rounded-2xl bg-slate-900 border border-amber-500/40 shadow-2xl space-y-4"
            >
              <div className="flex items-center gap-3 text-amber-400">
                <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20">
                  <AlertTriangle size={24} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Confirm Overlapping Slots</h3>
                  <p className="text-xs text-slate-400">Some class slots share overlapping times on the same day.</p>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-black/60 border border-amber-500/20 max-h-40 overflow-y-auto space-y-1 text-xs text-amber-300/90">
                {warnings.map((w, idx) => (
                  <p key={idx}>&bull; {w}</p>
                ))}
              </div>

              <p className="text-xs text-slate-300 leading-relaxed">
                As the administrator, you can choose to publish anyway (for split sessions, parallel labs, or elective blocks) or go back to adjust times.
              </p>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => setShowForcePublishModal(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white bg-white/5 hover:bg-white/10 transition-colors"
                >
                  Back to Edit
                </button>
                <button
                  onClick={() => handlePublish(true)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-black bg-amber-400 hover:bg-amber-300 transition-colors shadow-lg shadow-amber-500/20"
                >
                  Publish Anyway
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
