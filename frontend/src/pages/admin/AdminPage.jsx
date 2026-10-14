import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  School, Users, KeyRound, Copy, Check, Plus, Edit2,
  PowerOff, CheckCircle2, XCircle, RefreshCw, AlertCircle, X, Clock, Layers,
  UserPlus, FileSpreadsheet, Upload, Download, Search, Filter, ArrowRightLeft,
  UserCheck, UserX, ChevronLeft, ChevronRight, FileWarning, Eye, ShieldAlert
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../../hooks/useAuth';
import { institutionsAPI, adminStudentsAPI } from '../../api/client';

export default function AdminPage() {
  const { user, institution, refreshUser } = useAuth();

  const [activeTab, setActiveTab] = useState('classes'); // 'classes' | 'students' | 'requests'
  const [cohorts, setCohorts] = useState([]);
  const [joinRequests, setJoinRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Institution Join Code state
  const [joinCode, setJoinCode] = useState('');
  const [copiedCode, setCopiedCode] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  // Cohort Join Code state
  const [copiedCohortCodes, setCopiedCohortCodes] = useState({});
  const [regeneratingCohortId, setRegeneratingCohortId] = useState(null);
  const [togglingCohortId, setTogglingCohortId] = useState(null);

  // Class Modals
  const [showClassModal, setShowClassModal] = useState(false);
  const [editingCohort, setEditingCohort] = useState(null);
  const [classForm, setClassForm] = useState({
    name: '',
    level_type: 'college_year',
    level_value: 'SE',
    department: '',
    academic_year: '2026-27',
  });
  const [submittingClass, setSubmittingClass] = useState(false);

  // Approve modal
  const [approvingReq, setApprovingReq] = useState(null);
  const [assignedCohortId, setAssignedCohortId] = useState('');
  const [decidingId, setDecidingId] = useState(null);

  // ── Phase 6A: Students Tab State ─────────────────────────────
  const [students, setStudents] = useState([]);
  const [studentsTotal, setStudentsTotal] = useState(0);
  const [studentsPage, setStudentsPage] = useState(1);
  const [studentsTotalPages, setStudentsTotalPages] = useState(1);
  const [studentsLoading, setStudentsLoading] = useState(false);
  const [studentSearch, setStudentSearch] = useState('');
  const [studentCohortFilter, setStudentCohortFilter] = useState('');
  const [studentActiveFilter, setStudentActiveFilter] = useState('');

  // Single Student Creation Modal
  const [showAddStudentModal, setShowAddStudentModal] = useState(false);
  const [addStudentForm, setAddStudentForm] = useState({ full_name: '', email: '', cohort_id: '' });
  const [submittingAddStudent, setSubmittingAddStudent] = useState(false);
  const [oneTimeCredentials, setOneTimeCredentials] = useState(null);
  const [copiedPassword, setCopiedPassword] = useState(false);

  // Bulk Upload Modal
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [bulkStep, setBulkStep] = useState('upload'); // 'upload' | 'preview' | 'success'
  const [bulkFile, setBulkFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [uploadingPreview, setUploadingPreview] = useState(false);
  const [confirmingBulk, setConfirmingBulk] = useState(false);
  const [bulkCredentialsResult, setBulkCredentialsResult] = useState(null);

  // Move Class Modal
  const [moveStudentTarget, setMoveStudentTarget] = useState(null);
  const [targetCohortId, setTargetCohortId] = useState('');
  const [movingCohortLoading, setMovingCohortLoading] = useState(false);

  // Reset Password Modal
  const [resetPwdStudent, setResetPwdStudent] = useState(null);
  const [resetPwdLoading, setResetPwdLoading] = useState(false);
  const [newTempPasswordResult, setNewTempPasswordResult] = useState(null);

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [cohortsRes, reqsRes] = await Promise.all([
        institutionsAPI.listCohorts(),
        institutionsAPI.listJoinRequests({ status_filter: 'pending' }),
      ]);
      setCohorts(cohortsRes.data);
      setJoinRequests(reqsRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load institution data');
    } finally {
      setLoading(false);
    }
  }

  async function loadStudents(page = 1) {
    setStudentsLoading(true);
    try {
      const params = {
        page,
        page_size: 25,
      };
      if (studentSearch.trim()) params.search = studentSearch.trim();
      if (studentCohortFilter) params.cohort_id = studentCohortFilter;
      if (studentActiveFilter === 'active') params.is_active = true;
      if (studentActiveFilter === 'inactive') params.is_active = false;

      const res = await adminStudentsAPI.list(params);
      setStudents(res.data.items);
      setStudentsTotal(res.data.total);
      setStudentsPage(res.data.page);
      setStudentsTotalPages(res.data.total_pages);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load students');
    } finally {
      setStudentsLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    if (institution?.type === 'school') {
      setClassForm(prev => ({ ...prev, level_type: 'grade', level_value: '9' }));
    }
  }, [institution]);

  useEffect(() => {
    if (activeTab === 'students') {
      loadStudents(1);
    }
  }, [activeTab, studentCohortFilter, studentActiveFilter]);

  function copyCode(code) {
    if (!code) return;
    navigator.clipboard.writeText(code);
    setCopiedCode(true);
    toast.success('Join code copied to clipboard!');
    setTimeout(() => setCopiedCode(false), 2000);
  }

  function copyCohortCode(id, code) {
    if (!code) return;
    navigator.clipboard.writeText(code);
    setCopiedCohortCodes(prev => ({ ...prev, [id]: true }));
    toast.success(`Copied class code: ${code}`);
    setTimeout(() => {
      setCopiedCohortCodes(prev => ({ ...prev, [id]: false }));
    }, 2000);
  }

  async function handleRegenerateCohortCode(cohort) {
    if (!window.confirm(`Regenerate join code for class "${cohort.name}"? The previous code will stop working immediately.`)) {
      return;
    }
    setRegeneratingCohortId(cohort.id);
    try {
      await institutionsAPI.regenerateCohortJoinCode(cohort.id);
      toast.success('New class join code generated!');
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to regenerate class join code');
    } finally {
      setRegeneratingCohortId(null);
    }
  }

  async function handleToggleCohortCode(cohort) {
    setTogglingCohortId(cohort.id);
    try {
      const res = await institutionsAPI.toggleCohortJoinCode(cohort.id);
      toast.success(res.data.join_code_enabled ? 'Class join code enabled' : 'Class join code disabled');
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to toggle join code');
    } finally {
      setTogglingCohortId(null);
    }
  }

  async function handleRegenerateCode() {
    if (!window.confirm('Are you sure you want to regenerate the institution join code? The previous code will stop working immediately.')) {
      return;
    }

    setRegenerating(true);
    try {
      const res = await institutionsAPI.regenerateJoinCode();
      setJoinCode(res.data.join_code);
      toast.success('Generated new institution join code!');
      await refreshUser();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to regenerate join code');
    } finally {
      setRegenerating(false);
    }
  }

  function openCreateClass() {
    setEditingCohort(null);
    setClassForm({
      name: '',
      level_type: institution?.type === 'school' ? 'grade' : 'college_year',
      level_value: institution?.type === 'school' ? '9' : 'SE',
      department: '',
      academic_year: '2026-27',
    });
    setShowClassModal(true);
  }

  function openEditClass(cohort) {
    setEditingCohort(cohort);
    setClassForm({
      name: cohort.name,
      level_type: cohort.level_type,
      level_value: cohort.level_value,
      department: cohort.department || '',
      academic_year: cohort.academic_year,
    });
    setShowClassModal(true);
  }

  async function handleClassSubmit(e) {
    e.preventDefault();
    setSubmittingClass(true);
    try {
      if (editingCohort) {
        await institutionsAPI.updateCohort(editingCohort.id, {
          name: classForm.name,
          level_type: classForm.level_type,
          level_value: classForm.level_value,
          department: classForm.department || null,
          academic_year: classForm.academic_year,
        });
        toast.success('Class updated successfully');
      } else {
        await institutionsAPI.createCohort({
          name: classForm.name,
          level_type: classForm.level_type,
          level_value: classForm.level_value,
          department: classForm.department || null,
          academic_year: classForm.academic_year,
        });
        toast.success('Class created successfully');
      }
      setShowClassModal(false);
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save class');
    } finally {
      setSubmittingClass(false);
    }
  }

  async function handleDeactivateCohort(cohort) {
    if (!window.confirm(`Are you sure you want to deactivate "${cohort.name}"?`)) return;
    try {
      await institutionsAPI.deactivateCohort(cohort.id);
      toast.success('Class deactivated');
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to deactivate class');
    }
  }

  async function handleDecide(requestId, action, cohortId = null) {
    setDecidingId(requestId);
    try {
      await institutionsAPI.decideJoinRequest(requestId, {
        action,
        cohort_id: cohortId || undefined,
      });
      toast.success(action === 'approve' ? 'Student approved!' : 'Request rejected');
      setApprovingReq(null);
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || `Failed to ${action} request`);
    } finally {
      setDecidingId(null);
    }
  }

  // ── Phase 6A: Student Action Handlers ─────────────────────────

  async function handleCreateSingleStudent(e) {
    e.preventDefault();
    if (!addStudentForm.cohort_id) {
      toast.error('Please select a class for the student');
      return;
    }
    setSubmittingAddStudent(true);
    try {
      const res = await adminStudentsAPI.create(addStudentForm);
      setOneTimeCredentials(res.data);
      setShowAddStudentModal(false);
      setAddStudentForm({ full_name: '', email: '', cohort_id: '' });
      toast.success('Student created successfully!');
      loadStudents(1);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create student');
    } finally {
      setSubmittingAddStudent(false);
    }
  }

  async function handleDownloadTemplate() {
    try {
      const res = await adminStudentsAPI.downloadTemplate();
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'students_template.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Downloaded students template');
    } catch (err) {
      toast.error('Failed to download template');
    }
  }

  async function handlePreviewUpload(e) {
    e.preventDefault();
    if (!bulkFile) {
      toast.error('Please choose a .xlsx file');
      return;
    }
    setUploadingPreview(true);
    try {
      const res = await adminStudentsAPI.uploadPreview(bulkFile);
      setPreviewData(res.data);
      setBulkStep('preview');
      toast.success(`Parsed ${res.data.total_rows} rows: ${res.data.valid_count} valid, ${res.data.invalid_count} invalid`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to parse Excel file');
    } finally {
      setUploadingPreview(false);
    }
  }

  async function handleConfirmBulkUpload() {
    if (!previewData || !previewData.valid_rows.length) {
      toast.error('No valid rows to create');
      return;
    }
    setConfirmingBulk(true);
    try {
      const payload = {
        rows: previewData.valid_rows.map(r => ({
          full_name: r.full_name,
          email: r.email,
          cohort_id: r.cohort_id,
        })),
      };
      const res = await adminStudentsAPI.uploadConfirm(payload);
      setBulkCredentialsResult(res.data);
      setBulkStep('success');
      toast.success(`Successfully enrolled ${res.data.created_count} students!`);
      loadStudents(1);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to confirm bulk upload');
    } finally {
      setConfirmingBulk(false);
    }
  }

  async function handleDownloadErrorReport() {
    if (!previewData || !previewData.invalid_rows) return;
    try {
      const res = await adminStudentsAPI.downloadErrorReport(previewData.invalid_rows);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'upload_errors.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Downloaded error report');
    } catch (err) {
      toast.error('Failed to download error report');
    }
  }

  function handleDownloadCredentialsSheet(b64Data) {
    if (!b64Data) return;
    try {
      const byteCharacters = atob(b64Data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'student_credentials.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Downloaded credentials sheet');
    } catch (err) {
      toast.error('Failed to download credentials');
    }
  }

  async function handleResetPasswordExecute() {
    if (!resetPwdStudent) return;
    setResetPwdLoading(true);
    try {
      const res = await adminStudentsAPI.resetPassword(resetPwdStudent.id);
      setNewTempPasswordResult({
        student: resetPwdStudent,
        temp_pwd: res.data.temporary_password,
      });
      setResetPwdStudent(null);
      toast.success('Password reset successfully!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reset password');
    } finally {
      setResetPwdLoading(false);
    }
  }

  async function handleToggleStudentStatus(student) {
    const isActivating = !student.is_active;
    const actionLabel = isActivating ? 'reactivate' : 'deactivate';
    if (!window.confirm(`Are you sure you want to ${actionLabel} ${student.full_name || student.email}?`)) {
      return;
    }
    try {
      if (isActivating) {
        await adminStudentsAPI.reactivate(student.id);
        toast.success('Student reactivated');
      } else {
        await adminStudentsAPI.deactivate(student.id);
        toast.success('Student deactivated');
      }
      loadStudents(studentsPage);
    } catch (err) {
      toast.error(err.response?.data?.detail || `Failed to ${actionLabel} student`);
    }
  }

  async function handleMoveCohortSubmit(e) {
    e.preventDefault();
    if (!targetCohortId) {
      toast.error('Please select a target class');
      return;
    }
    setMovingCohortLoading(true);
    try {
      await adminStudentsAPI.moveCohort(moveStudentTarget.id, targetCohortId);
      toast.success('Student moved to new class');
      setMoveStudentTarget(null);
      setTargetCohortId('');
      loadStudents(studentsPage);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to move student');
    } finally {
      setMovingCohortLoading(false);
    }
  }

  const currentJoinCode = joinCode || institution?.join_code;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      {/* Institution Banner & Join Code */}
      <div className="mb-8 p-6 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-500/20 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Institution Admin
              </span>
              <span className="text-xs text-slate-400 capitalize">{institution?.type || 'Institution'}</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              {institution?.name || 'My Institution'}
            </h1>
            {institution?.location && (
              <p className="text-xs text-slate-400 mt-0.5">{institution.location}</p>
            )}
          </div>

          {/* Institution Join Code Box */}
          <div className="p-3.5 rounded-xl bg-black/60 border border-emerald-500/30 flex items-center gap-4 self-start md:self-auto">
            <div>
              <p className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                Institution Join Code
              </p>
              <p className="font-mono text-xl font-bold text-emerald-400 tracking-wider">
                {currentJoinCode || '••••••••'}
              </p>
            </div>
            <div className="flex items-center gap-1.5 pl-2 border-l border-white/10">
              <button
                onClick={() => copyCode(currentJoinCode)}
                className="p-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded-lg transition-colors"
                title="Copy Institution Code"
              >
                {copiedCode ? <Check size={16} /> : <Copy size={16} />}
              </button>
              <button
                onClick={handleRegenerateCode}
                disabled={regenerating}
                className="p-2 bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white rounded-lg transition-colors"
                title="Regenerate Institution Code"
              >
                <RefreshCw size={16} className={regenerating ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-white/10 mb-6 overflow-x-auto">
        <button
          onClick={() => setActiveTab('classes')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 whitespace-nowrap transition-all ${
            activeTab === 'classes'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers size={16} />
          <span>Classes / Cohorts</span>
          <span className="px-1.5 py-0.5 rounded text-[11px] bg-white/10 text-slate-300">
            {cohorts.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('students')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 whitespace-nowrap transition-all ${
            activeTab === 'students'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Users size={16} />
          <span>Students</span>
          <span className="px-1.5 py-0.5 rounded text-[11px] bg-emerald-500/20 text-emerald-400 font-mono">
            {studentsTotal}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('requests')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 whitespace-nowrap transition-all ${
            activeTab === 'requests'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Clock size={16} />
          <span>Join Requests</span>
          {joinRequests.length > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[11px] bg-emerald-500 text-black font-bold">
              {joinRequests.length}
            </span>
          )}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm flex items-center gap-3">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          TAB 1: CLASSES
      ───────────────────────────────────────────────────────────── */}
      {activeTab === 'classes' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white">Class Cohorts</h2>
              <p className="text-xs text-slate-400">
                Manage divisions, grades, or college academic years with unique class join codes.
              </p>
            </div>
            <button
              onClick={openCreateClass}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5 shadow-lg shadow-emerald-500/20"
            >
              <Plus size={16} /> Add Class
            </button>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-500 text-sm">Loading classes...</div>
          ) : cohorts.length === 0 ? (
            <div className="p-12 rounded-2xl bg-slate-900/50 border border-white/5 text-center">
              <School size={36} className="mx-auto text-slate-600 mb-3" />
              <p className="text-slate-300 font-medium text-sm">No classes created yet</p>
              <p className="text-slate-500 text-xs mt-1">
                Create classes (e.g. SE Comps, Grade 10-A) to organize students.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {cohorts.map((cohort) => (
                <div
                  key={cohort.id}
                  className={`p-5 rounded-2xl border transition-all ${
                    cohort.is_active
                      ? 'bg-slate-900/60 border-white/10 hover:border-emerald-500/30'
                      : 'bg-slate-900/20 border-white/5 opacity-60'
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-bold text-white text-base">{cohort.name}</h3>
                      <p className="text-xs text-slate-400">
                        {cohort.level_type === 'grade' ? `Grade ${cohort.level_value}` : cohort.level_value}
                        {cohort.department && ` • ${cohort.department}`}
                      </p>
                    </div>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/10">
                      {cohort.academic_year}
                    </span>
                  </div>

                  {/* Class Join Code Section */}
                  {cohort.join_code && (
                    <div className="my-3 p-3 rounded-xl bg-black/50 border border-white/10 flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                            Class Join Code
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.2 rounded font-semibold ${
                            cohort.join_code_enabled
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          }`}>
                            {cohort.join_code_enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </div>
                        <p className={`font-mono text-base font-bold tracking-wider mt-0.5 ${
                          cohort.join_code_enabled ? 'text-emerald-400' : 'text-slate-500 line-through'
                        }`}>
                          {cohort.join_code}
                        </p>
                      </div>

                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => copyCohortCode(cohort.id, cohort.join_code)}
                          className="p-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded-lg transition-colors"
                          title="Copy Class Code"
                        >
                          {copiedCohortCodes[cohort.id] ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                        <button
                          onClick={() => handleRegenerateCohortCode(cohort)}
                          disabled={regeneratingCohortId === cohort.id}
                          className="p-1.5 bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white rounded-lg transition-colors"
                          title="Regenerate Class Code"
                        >
                          <RefreshCw size={14} className={regeneratingCohortId === cohort.id ? 'animate-spin' : ''} />
                        </button>
                        <button
                          onClick={() => handleToggleCohortCode(cohort)}
                          disabled={togglingCohortId === cohort.id}
                          className={`p-1.5 rounded-lg transition-colors ${
                            cohort.join_code_enabled
                              ? 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400'
                              : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400'
                          }`}
                          title={cohort.join_code_enabled ? 'Disable Code' : 'Enable Code'}
                        >
                          <PowerOff size={14} />
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/5">
                    <button
                      onClick={() => openEditClass(cohort)}
                      className="p-1.5 text-slate-400 hover:text-emerald-400 transition-colors"
                      title="Edit class"
                    >
                      <Edit2 size={15} />
                    </button>
                    {cohort.is_active && (
                      <button
                        onClick={() => handleDeactivateCohort(cohort)}
                        className="p-1.5 text-slate-400 hover:text-rose-400 transition-colors"
                        title="Deactivate class"
                      >
                        <PowerOff size={15} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          TAB 2: STUDENTS (PHASE 6A)
      ───────────────────────────────────────────────────────────── */}
      {activeTab === 'students' && (
        <div>
          {/* Header & Primary Actions */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h2 className="text-lg font-bold text-white">Students Directory</h2>
              <p className="text-xs text-slate-400">
                Enroll, manage, and assign students belonging to {institution?.name || 'your institution'}.
              </p>
            </div>
            <div className="flex items-center gap-2 self-start sm:self-auto">
              <button
                onClick={handleDownloadTemplate}
                className="px-3.5 py-2 bg-white/5 hover:bg-white/10 text-slate-300 font-medium text-xs rounded-xl transition-colors flex items-center gap-1.5 border border-white/10"
                title="Download Excel Template"
              >
                <Download size={14} /> Template
              </button>
              <button
                onClick={() => {
                  setBulkStep('upload');
                  setBulkFile(null);
                  setPreviewData(null);
                  setBulkCredentialsResult(null);
                  setShowBulkModal(true);
                }}
                className="px-3.5 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 font-medium text-xs rounded-xl transition-colors flex items-center gap-1.5"
              >
                <FileSpreadsheet size={15} /> Upload Excel
              </button>
              <button
                onClick={() => setShowAddStudentModal(true)}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5 shadow-lg shadow-emerald-500/20"
              >
                <UserPlus size={15} /> Add Student
              </button>
            </div>
          </div>

          {/* Search & Filter Bar */}
          <div className="mb-6 p-4 rounded-xl bg-slate-900/60 border border-white/10 flex flex-col md:flex-row items-stretch md:items-center gap-3">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={studentSearch}
                onChange={(e) => setStudentSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadStudents(1)}
                placeholder="Search by student name, email, or username..."
                className="w-full pl-9 pr-4 py-2 bg-black/40 border border-white/10 rounded-lg text-white placeholder-slate-500 text-xs focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <select
                value={studentCohortFilter}
                onChange={(e) => setStudentCohortFilter(e.target.value)}
                className="px-3 py-2 bg-black/40 border border-white/10 rounded-lg text-white text-xs focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Classes</option>
                {cohorts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>

              <select
                value={studentActiveFilter}
                onChange={(e) => setStudentActiveFilter(e.target.value)}
                className="px-3 py-2 bg-black/40 border border-white/10 rounded-lg text-white text-xs focus:outline-none focus:border-emerald-500"
              >
                <option value="">All Statuses</option>
                <option value="active">Active Only</option>
                <option value="inactive">Archived / Inactive</option>
              </select>

              <button
                onClick={() => loadStudents(1)}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-300 font-medium text-xs rounded-lg transition-colors"
              >
                Apply
              </button>
            </div>
          </div>

          {/* Students Table */}
          {studentsLoading ? (
            <div className="p-12 text-center text-slate-500 text-sm flex items-center justify-center gap-2">
              <RefreshCw size={16} className="animate-spin text-emerald-400" /> Loading students directory...
            </div>
          ) : students.length === 0 ? (
            <div className="p-12 rounded-2xl bg-slate-900/50 border border-white/5 text-center">
              <Users size={36} className="mx-auto text-slate-600 mb-3" />
              <p className="text-slate-300 font-medium text-sm">No students found</p>
              <p className="text-slate-500 text-xs mt-1">
                Add students individually or upload an Excel roster to populate your institution.
              </p>
            </div>
          ) : (
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-black/40 text-slate-400 uppercase tracking-wider font-semibold border-b border-white/10">
                    <tr>
                      <th className="px-5 py-3">Student Name</th>
                      <th className="px-5 py-3">Username & Email</th>
                      <th className="px-5 py-3">Assigned Class</th>
                      <th className="px-5 py-3">Status</th>
                      <th className="px-5 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {students.map((student) => (
                      <tr key={student.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-bold flex items-center justify-center text-xs">
                              {(student.full_name || student.username || 'S')[0].toUpperCase()}
                            </div>
                            <div>
                              <p className="font-semibold text-white text-sm">
                                {student.full_name || 'No name'}
                              </p>
                              {student.created_by_admin && (
                                <span className="text-[10px] text-slate-500">Admin-enrolled</span>
                              )}
                            </div>
                          </div>
                        </td>

                        <td className="px-5 py-3.5">
                          <p className="font-mono text-xs text-slate-300 font-medium">{student.username}</p>
                          <p className="text-slate-500 text-[11px]">{student.email}</p>
                        </td>

                        <td className="px-5 py-3.5">
                          {student.cohort_name ? (
                            <span className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                              {student.cohort_name}
                            </span>
                          ) : (
                            <span className="text-slate-500 text-[11px] italic">Unassigned</span>
                          )}
                        </td>

                        <td className="px-5 py-3.5">
                          {student.is_active ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
                              <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span> Inactive / Archived
                            </span>
                          )}
                        </td>

                        <td className="px-5 py-3.5 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => {
                                setMoveStudentTarget(student);
                                setTargetCohortId(student.cohort_id || '');
                              }}
                              className="p-1.5 hover:bg-white/10 text-slate-400 hover:text-white rounded-lg transition-colors"
                              title="Move to another class"
                            >
                              <ArrowRightLeft size={14} />
                            </button>

                            <button
                              onClick={() => setResetPwdStudent(student)}
                              className="p-1.5 hover:bg-white/10 text-slate-400 hover:text-amber-400 rounded-lg transition-colors"
                              title="Reset Password"
                            >
                              <KeyRound size={14} />
                            </button>

                            <button
                              onClick={() => handleToggleStudentStatus(student)}
                              className={`p-1.5 rounded-lg transition-colors ${
                                student.is_active
                                  ? 'hover:bg-rose-500/10 text-slate-400 hover:text-rose-400'
                                  : 'hover:bg-emerald-500/10 text-slate-400 hover:text-emerald-400'
                              }`}
                              title={student.is_active ? 'Deactivate student' : 'Reactivate student'}
                            >
                              {student.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination controls */}
              <div className="px-5 py-3 bg-black/40 border-t border-white/5 flex items-center justify-between text-xs text-slate-400">
                <p>
                  Showing {students.length} of {studentsTotal} student{studentsTotal === 1 ? '' : 's'}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadStudents(studentsPage - 1)}
                    disabled={studentsPage <= 1}
                    className="p-1.5 rounded bg-white/5 hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed text-slate-300"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <span className="font-mono text-slate-300 font-semibold px-2">
                    {studentsPage} / {studentsTotalPages || 1}
                  </span>
                  <button
                    onClick={() => loadStudents(studentsPage + 1)}
                    disabled={studentsPage >= studentsTotalPages}
                    className="p-1.5 rounded bg-white/5 hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed text-slate-300"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          TAB 3: JOIN REQUESTS
      ───────────────────────────────────────────────────────────── */}
      {activeTab === 'requests' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white">Pending Join Requests</h2>
              <p className="text-xs text-slate-400">Students waiting for approval to access your institution.</p>
            </div>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-500 text-sm">Loading requests...</div>
          ) : joinRequests.length === 0 ? (
            <div className="p-12 rounded-2xl bg-slate-900/50 border border-white/5 text-center">
              <CheckCircle2 size={36} className="mx-auto text-emerald-500/50 mb-3" />
              <p className="text-slate-300 font-medium text-sm">No pending join requests</p>
              <p className="text-slate-500 text-xs mt-1">All student access requests have been processed.</p>
            </div>
          ) : (
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 overflow-hidden">
              <div className="divide-y divide-white/5">
                {joinRequests.map((req) => {
                  const isClassReq = req.request_type === 'class';
                  return (
                    <div key={req.id} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-white/[0.02] transition-colors">
                      <div>
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <span className="font-semibold text-white text-sm">
                            {req.user_full_name || req.user_username || 'Student'}
                          </span>
                          <span className="text-xs text-slate-500 font-mono">({req.user_email})</span>
                          {isClassReq ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                              Class Request: {req.requested_cohort_name || 'Class'}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20">
                              Institution Request
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-500">
                          Requested on {new Date(req.created_at).toLocaleDateString()}
                          {isClassReq && req.requested_cohort_name && (
                            <span className="ml-2 text-slate-400">Target Class: <strong className="text-emerald-400">{req.requested_cohort_name}</strong></span>
                          )}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 self-end sm:self-auto">
                        <button
                          onClick={() => handleDecide(req.id, 'reject')}
                          disabled={decidingId === req.id}
                          className="px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1"
                        >
                          <XCircle size={14} /> Reject
                        </button>
                        <button
                          onClick={() => handleDecide(req.id, 'approve')}
                          disabled={decidingId === req.id}
                          className="px-3.5 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-lg transition-colors flex items-center gap-1"
                        >
                          <CheckCircle2 size={14} />
                          {isClassReq
                            ? `Approve into ${req.requested_cohort_name || 'Class'}`
                            : 'Approve Institution'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          MODAL: CREATE / EDIT CLASS
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showClassModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setShowClassModal(false)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <h3 className="text-lg font-bold text-white mb-4">
                {editingCohort ? 'Edit Class Cohort' : 'Create New Class'}
              </h3>

              <form onSubmit={handleClassSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Class Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={classForm.name}
                    onChange={(e) => setClassForm({ ...classForm, name: e.target.value })}
                    placeholder="e.g. SE Computer Engineering 2026"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Level Type
                    </label>
                    <select
                      value={classForm.level_type}
                      onChange={(e) => setClassForm({ ...classForm, level_type: e.target.value })}
                      className="w-full px-3 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-emerald-500"
                    >
                      <option value="grade">School Grade</option>
                      <option value="college_year">College Year</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Level Value *
                    </label>
                    <input
                      type="text"
                      required
                      value={classForm.level_value}
                      onChange={(e) => setClassForm({ ...classForm, level_value: e.target.value })}
                      placeholder="e.g. 10 or SE"
                      className="w-full px-3 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Department / Branch (Optional)
                  </label>
                  <input
                    type="text"
                    value={classForm.department}
                    onChange={(e) => setClassForm({ ...classForm, department: e.target.value })}
                    placeholder="e.g. Computer Engineering"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Academic Year *
                  </label>
                  <input
                    type="text"
                    required
                    value={classForm.academic_year}
                    onChange={(e) => setClassForm({ ...classForm, academic_year: e.target.value })}
                    placeholder="e.g. 2026-27"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowClassModal(false)}
                    className="px-4 py-2 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingClass}
                    className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors"
                  >
                    {submittingClass ? 'Saving...' : editingCohort ? 'Update Class' : 'Create Class'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: ADD SINGLE STUDENT
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showAddStudentModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setShowAddStudentModal(false)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <div className="flex items-center gap-2 mb-2">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                  <UserPlus size={18} />
                </div>
                <h3 className="text-lg font-bold text-white">Enroll New Student</h3>
              </div>
              <p className="text-xs text-slate-400 mb-4">
                Enrolled students will be fully approved with an auto-generated username and secure temporary password.
              </p>

              <form onSubmit={handleCreateSingleStudent} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Student Full Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={addStudentForm.full_name}
                    onChange={(e) => setAddStudentForm({ ...addStudentForm, full_name: e.target.value })}
                    placeholder="e.g. Diya Patel"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Email Address *
                  </label>
                  <input
                    type="email"
                    required
                    value={addStudentForm.email}
                    onChange={(e) => setAddStudentForm({ ...addStudentForm, email: e.target.value })}
                    placeholder="e.g. diya.patel@example.com"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Class Cohort *
                  </label>
                  <select
                    required
                    value={addStudentForm.cohort_id}
                    onChange={(e) => setAddStudentForm({ ...addStudentForm, cohort_id: e.target.value })}
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">Select class cohort...</option>
                    {cohorts.filter(c => c.is_active).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.academic_year})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowAddStudentModal(false)}
                    className="px-4 py-2 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingAddStudent}
                    className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5"
                  >
                    {submittingAddStudent ? <RefreshCw size={14} className="animate-spin" /> : <UserPlus size={14} />}
                    {submittingAddStudent ? 'Enrolling...' : 'Enroll Student'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: ONE-TIME CREDENTIALS DISPLAY
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {oneTimeCredentials && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-emerald-500/30 rounded-2xl shadow-2xl relative"
            >
              <div className="p-3 mb-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-start gap-3">
                <ShieldAlert size={18} className="shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-semibold">One-Time Temporary Credentials</p>
                  <p className="mt-0.5 text-amber-400/80">
                    This temporary password is never stored in plain text and will not be displayed again. Please copy and provide it to the student.
                  </p>
                </div>
              </div>

              <div className="space-y-3 p-4 rounded-xl bg-black/50 border border-white/10 text-xs">
                <div>
                  <span className="text-slate-500 uppercase text-[10px] tracking-wider font-semibold">Student Name</span>
                  <p className="text-white font-medium text-sm">{oneTimeCredentials.full_name}</p>
                </div>
                <div>
                  <span className="text-slate-500 uppercase text-[10px] tracking-wider font-semibold">Username</span>
                  <p className="text-white font-mono text-sm">{oneTimeCredentials.username}</p>
                </div>
                <div>
                  <span className="text-slate-500 uppercase text-[10px] tracking-wider font-semibold">Email</span>
                  <p className="text-white font-mono">{oneTimeCredentials.email}</p>
                </div>
                <div>
                  <span className="text-slate-500 uppercase text-[10px] tracking-wider font-semibold">Class</span>
                  <p className="text-emerald-400 font-medium">{oneTimeCredentials.class_name}</p>
                </div>
                <div className="pt-2 border-t border-white/10 flex items-center justify-between">
                  <div>
                    <span className="text-slate-500 uppercase text-[10px] tracking-wider font-semibold">Temporary Password</span>
                    <p className="font-mono text-base font-bold text-emerald-400 tracking-wider">
                      {oneTimeCredentials.temporary_password}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(oneTimeCredentials.temporary_password);
                      setCopiedPassword(true);
                      toast.success('Temporary password copied!');
                      setTimeout(() => setCopiedPassword(false), 2000);
                    }}
                    className="p-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    {copiedPassword ? <Check size={15} /> : <Copy size={15} />}
                    <span className="text-xs font-semibold">{copiedPassword ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => setOneTimeCredentials(null)}
                  className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl transition-colors"
                >
                  I Have Saved Credentials
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: BULK UPLOAD MULTI-STEP FLOW
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showBulkModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-2xl max-h-[85vh] flex flex-col p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setShowBulkModal(false)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <div className="flex items-center gap-2 mb-1">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                  <FileSpreadsheet size={18} />
                </div>
                <h3 className="text-lg font-bold text-white">Bulk Student Enrollment (.xlsx)</h3>
              </div>
              <p className="text-xs text-slate-400 mb-4">
                Upload your student roster spreadsheet with columns: <strong>Full Name</strong>, <strong>Email</strong>, and <strong>Class</strong>.
              </p>

              {/* STEP 1: UPLOAD */}
              {bulkStep === 'upload' && (
                <form onSubmit={handlePreviewUpload} className="space-y-4">
                  <div className="p-6 border-2 border-dashed border-white/10 hover:border-emerald-500/50 rounded-2xl text-center bg-black/30 transition-colors">
                    <Upload size={32} className="mx-auto text-emerald-400/80 mb-3" />
                    <label className="cursor-pointer">
                      <span className="px-4 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-semibold text-xs rounded-lg transition-colors inline-block mb-2">
                        Browse Excel File
                      </span>
                      <input
                        type="file"
                        accept=".xlsx"
                        onChange={(e) => setBulkFile(e.target.files?.[0] || null)}
                        className="hidden"
                      />
                    </label>
                    <p className="text-xs text-slate-300 font-medium">
                      {bulkFile ? bulkFile.name : 'Choose a .xlsx file (max 2 MB, up to 500 rows)'}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-2">
                    <button
                      type="button"
                      onClick={handleDownloadTemplate}
                      className="text-xs text-emerald-400 hover:underline flex items-center gap-1"
                    >
                      <Download size={14} /> Need sample template? Download here
                    </button>

                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setShowBulkModal(false)}
                        className="px-4 py-2 text-xs text-slate-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={!bulkFile || uploadingPreview}
                        className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5"
                      >
                        {uploadingPreview ? <RefreshCw size={14} className="animate-spin" /> : <Eye size={14} />}
                        {uploadingPreview ? 'Parsing File...' : 'Preview Roster'}
                      </button>
                    </div>
                  </div>
                </form>
              )}

              {/* STEP 2: PREVIEW */}
              {bulkStep === 'preview' && previewData && (
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                      <span className="text-[10px] text-slate-500 font-semibold uppercase">Total Rows</span>
                      <p className="text-lg font-bold text-white font-mono">{previewData.total_rows}</p>
                    </div>
                    <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                      <span className="text-[10px] text-emerald-400 font-semibold uppercase">Valid to Enroll</span>
                      <p className="text-lg font-bold text-emerald-400 font-mono">{previewData.valid_count}</p>
                    </div>
                    <div className="p-3 rounded-xl bg-rose-500/5 border border-rose-500/20">
                      <span className="text-[10px] text-rose-400 font-semibold uppercase">Invalid Rows</span>
                      <p className="text-lg font-bold text-rose-400 font-mono">{previewData.invalid_count}</p>
                    </div>
                  </div>

                  {previewData.invalid_count > 0 && (
                    <div className="mb-3 flex items-center justify-between p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                      <div className="flex items-center gap-2">
                        <FileWarning size={15} />
                        <span>{previewData.invalid_count} row(s) have errors and will be skipped.</span>
                      </div>
                      <button
                        onClick={handleDownloadErrorReport}
                        className="px-2.5 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded text-[11px] font-semibold transition-colors flex items-center gap-1"
                      >
                        <Download size={13} /> Download Error Report
                      </button>
                    </div>
                  )}

                  {/* Preview Table */}
                  <div className="flex-1 overflow-y-auto border border-white/10 rounded-xl bg-black/40 mb-4 max-h-[35vh]">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-900 sticky top-0 text-slate-400 text-[10px] uppercase font-semibold border-b border-white/10">
                        <tr>
                          <th className="px-3 py-2">Row</th>
                          <th className="px-3 py-2">Name</th>
                          <th className="px-3 py-2">Email</th>
                          <th className="px-3 py-2">Class</th>
                          <th className="px-3 py-2">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {[...previewData.valid_rows, ...previewData.invalid_rows]
                          .sort((a, b) => a.row_num - b.row_num)
                          .map((row) => (
                            <tr key={row.row_num} className={row.valid ? 'hover:bg-white/[0.02]' : 'bg-rose-500/[0.03]'}>
                              <td className="px-3 py-2 font-mono text-slate-500">#{row.row_num}</td>
                              <td className="px-3 py-2 font-medium text-white">{row.full_name}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{row.email}</td>
                              <td className="px-3 py-2 text-slate-300">{row.class_name}</td>
                              <td className="px-3 py-2">
                                {row.valid ? (
                                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                    Ready
                                  </span>
                                ) : (
                                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20" title={row.reason}>
                                    {row.reason}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-white/10">
                    <button
                      onClick={() => setBulkStep('upload')}
                      className="px-4 py-2 text-xs text-slate-400 hover:text-white"
                    >
                      Back to Upload
                    </button>
                    <button
                      onClick={handleConfirmBulkUpload}
                      disabled={confirmingBulk || previewData.valid_count === 0}
                      className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5"
                    >
                      {confirmingBulk ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                      {confirmingBulk ? 'Enrolling Students...' : `Confirm & Enroll ${previewData.valid_count} Students`}
                    </button>
                  </div>
                </div>
              )}

              {/* STEP 3: SUCCESS & ONE-TIME CREDENTIALS SHEET */}
              {bulkStep === 'success' && bulkCredentialsResult && (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-center">
                    <CheckCircle2 size={36} className="mx-auto text-emerald-400 mb-2" />
                    <h4 className="text-base font-bold text-white">Enrollment Completed</h4>
                    <p className="text-xs text-slate-300 mt-1">
                      Enrolled <strong>{bulkCredentialsResult.created_count}</strong> students with unique usernames and temporary passwords.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
                    <p className="font-semibold flex items-center gap-1.5">
                      <ShieldAlert size={16} /> Important Security Notice
                    </p>
                    <p className="mt-1 text-amber-400/80">
                      The generated credentials sheet contains temporary passwords that are only held in memory right now. Once you close this modal, you will not be able to download this sheet again.
                    </p>
                  </div>

                  <div className="flex items-center justify-center py-2">
                    <button
                      onClick={() => handleDownloadCredentialsSheet(bulkCredentialsResult.credentials_file_b64)}
                      className="px-6 py-3 bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-sm rounded-xl transition-all shadow-xl shadow-emerald-500/20 flex items-center gap-2"
                    >
                      <Download size={18} /> Download Credentials Sheet (.xlsx)
                    </button>
                  </div>

                  <div className="flex justify-end pt-2 border-t border-white/10">
                    <button
                      onClick={() => setShowBulkModal(false)}
                      className="px-5 py-2.5 bg-white/10 hover:bg-white/20 text-white font-medium text-xs rounded-xl transition-colors"
                    >
                      Done & Close
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: MOVE CLASS
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {moveStudentTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setMoveStudentTarget(null)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <h3 className="text-lg font-bold text-white mb-2">Move Student to Class</h3>
              <p className="text-xs text-slate-400 mb-4">
                Select the target class cohort within {institution?.name || 'your institution'} for <strong className="text-white">{moveStudentTarget.full_name || moveStudentTarget.username}</strong>:
              </p>

              <form onSubmit={handleMoveCohortSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Target Class Cohort *
                  </label>
                  <select
                    required
                    value={targetCohortId}
                    onChange={(e) => setTargetCohortId(e.target.value)}
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">Select target class...</option>
                    {cohorts.filter(c => c.is_active).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.academic_year})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setMoveStudentTarget(null)}
                    className="px-4 py-2 text-xs text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={movingCohortLoading || !targetCohortId}
                    className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5"
                  >
                    {movingCohortLoading ? <RefreshCw size={14} className="animate-spin" /> : <ArrowRightLeft size={14} />}
                    {movingCohortLoading ? 'Moving...' : 'Move to Class'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: RESET PASSWORD CONFIRM & RESULT
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {resetPwdStudent && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setResetPwdStudent(null)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <h3 className="text-lg font-bold text-white mb-2">Reset Student Password</h3>
              <p className="text-xs text-slate-300 mb-4">
                Are you sure you want to generate a new temporary password for <strong>{resetPwdStudent.full_name || resetPwdStudent.email}</strong>?
              </p>
              <div className="p-3 mb-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
                This will immediately invalidate any active login sessions for this student. They will be required to choose a new password on their next login.
              </div>

              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setResetPwdStudent(null)}
                  className="px-4 py-2 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  onClick={handleResetPasswordExecute}
                  disabled={resetPwdLoading}
                  className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5"
                >
                  {resetPwdLoading ? <RefreshCw size={14} className="animate-spin" /> : <KeyRound size={14} />}
                  {resetPwdLoading ? 'Resetting...' : 'Generate New Password'}
                </button>
              </div>
            </motion.div>
          </div>
        )}

        {newTempPasswordResult && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-emerald-500/30 rounded-2xl shadow-2xl relative"
            >
              <h3 className="text-lg font-bold text-white mb-2">New Temporary Password</h3>
              <p className="text-xs text-slate-400 mb-4">
                Password reset for <strong className="text-white">{newTempPasswordResult.student.full_name || newTempPasswordResult.student.username}</strong>:
              </p>

              <div className="p-4 rounded-xl bg-black/50 border border-white/10 flex items-center justify-between mb-4">
                <p className="font-mono text-lg font-bold text-emerald-400 tracking-wider">
                  {newTempPasswordResult.temp_pwd}
                </p>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(newTempPasswordResult.temp_pwd);
                    setCopiedPassword(true);
                    toast.success('Password copied!');
                    setTimeout(() => setCopiedPassword(false), 2000);
                  }}
                  className="p-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded-lg transition-colors flex items-center gap-1"
                >
                  {copiedPassword ? <Check size={15} /> : <Copy size={15} />}
                  <span className="text-xs font-semibold">{copiedPassword ? 'Copied' : 'Copy'}</span>
                </button>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={() => setNewTempPasswordResult(null)}
                  className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl transition-colors"
                >
                  Done
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: APPROVE JOIN REQUEST WITH CLASS ASSIGNMENT
      ───────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {approvingReq && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-emerald-500/30 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setApprovingReq(null)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <h3 className="text-lg font-bold text-white mb-2">Approve Student Enrollment</h3>
              <p className="text-xs text-slate-400 mb-4">
                Assign a class cohort for <span className="text-white font-medium">{approvingReq.user_full_name || approvingReq.user_username}</span>:
              </p>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Assign Class
                  </label>
                  <select
                    value={assignedCohortId}
                    onChange={(e) => setAssignedCohortId(e.target.value)}
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">No class assignment (general membership)</option>
                    {cohorts.filter(c => c.is_active).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.academic_year})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setApprovingReq(null)}
                    className="px-4 py-2 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleDecide(approvingReq.id, 'approve', assignedCohortId)}
                    disabled={decidingId === approvingReq.id}
                    className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors flex items-center gap-1.5"
                  >
                    <CheckCircle2 size={15} /> Confirm Approval
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
