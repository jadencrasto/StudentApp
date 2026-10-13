import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  School, Users, KeyRound, Copy, Check, Plus, Edit2,
  PowerOff, CheckCircle2, XCircle, RefreshCw, AlertCircle, X, Clock, Layers
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../../hooks/useAuth';
import { institutionsAPI } from '../../api/client';

export default function AdminPage() {
  const { user, institution, refreshUser } = useAuth();

  const [activeTab, setActiveTab] = useState('classes'); // 'classes' | 'requests'
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

  // Modals
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

  useEffect(() => {
    loadData();
    // Default level_type based on institution type
    if (institution?.type === 'school') {
      setClassForm(prev => ({ ...prev, level_type: 'grade', level_value: '9' }));
    }
  }, [institution]);

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

  function openEditClass(c) {
    setEditingCohort(c);
    setClassForm({
      name: c.name,
      level_type: c.level_type,
      level_value: c.level_value,
      department: c.department || '',
      academic_year: c.academic_year,
    });
    setShowClassModal(true);
  }

  async function handleClassSubmit(e) {
    e.preventDefault();
    if (!classForm.name.trim()) return;

    setSubmittingClass(true);
    try {
      if (editingCohort) {
        await institutionsAPI.updateCohort(editingCohort.id, {
          name: classForm.name.trim(),
          level_type: classForm.level_type,
          level_value: classForm.level_value.trim(),
          department: classForm.department.trim() || undefined,
          academic_year: classForm.academic_year.trim(),
        });
        toast.success('Class updated!');
      } else {
        await institutionsAPI.createCohort({
          name: classForm.name.trim(),
          level_type: classForm.level_type,
          level_value: classForm.level_value.trim(),
          department: classForm.department.trim() || undefined,
          academic_year: classForm.academic_year.trim(),
        });
        toast.success('Class created!');
      }
      setShowClassModal(false);
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save class');
    } finally {
      setSubmittingClass(false);
    }
  }

  async function handleDeactivateClass(cohort) {
    if (!window.confirm(`Deactivate class "${cohort.name}"?`)) return;

    try {
      await institutionsAPI.deactivateCohort(cohort.id);
      toast.success(`Class ${cohort.name} deactivated`);
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
      toast.success(action === 'approve' ? 'Student approved!' : 'Join request rejected');
      setApprovingReq(null);
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update request');
    } finally {
      setDecidingId(null);
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
      <div className="flex items-center gap-2 border-b border-white/10 mb-6">
        <button
          onClick={() => setActiveTab('classes')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
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
          onClick={() => setActiveTab('requests')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'requests'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Users size={16} />
          <span>Join Requests</span>
          {joinRequests.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[11px] bg-amber-500 text-black font-bold">
              {joinRequests.length}
            </span>
          )}
        </button>
      </div>

      {/* TAB 1: CLASSES */}
      {activeTab === 'classes' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-white">Active Classes & Batches</h2>
              <p className="text-xs text-slate-400">Manage cohorts, class join codes, and student enrollment</p>
            </div>
            <button
              onClick={openCreateClass}
              className="px-3.5 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl flex items-center gap-1.5 transition-colors"
            >
              <Plus size={15} /> Add Class
            </button>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-500 text-sm">
              <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              Loading classes...
            </div>
          ) : cohorts.length === 0 ? (
            <div className="p-12 text-center rounded-2xl bg-white/[0.02] border border-white/10">
              <Layers size={36} className="mx-auto text-slate-600 mb-3" />
              <p className="text-sm text-slate-300 font-medium">No classes created yet</p>
              <p className="text-xs text-slate-500 mt-1">Create your first class cohort to organize students.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {cohorts.map((c) => (
                <div
                  key={c.id}
                  className={`p-5 rounded-2xl border transition-all flex flex-col justify-between ${
                    c.is_active
                      ? 'bg-white/[0.02] border-white/10 hover:border-emerald-500/30'
                      : 'bg-white/[0.01] border-white/5 opacity-60'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div>
                        <h3 className="font-semibold text-white text-base">{c.name}</h3>
                        <p className="text-xs text-slate-400">{c.academic_year}</p>
                      </div>
                      <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${
                        c.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-700 text-slate-400'
                      }`}>
                        {c.is_active ? 'Active' : 'Archived'}
                      </span>
                    </div>

                    <div className="space-y-1 my-2 text-xs text-slate-400">
                      <p>
                        <span className="text-slate-500">Level:</span> {c.level_type === 'grade' ? `Grade ${c.level_value}` : `Year ${c.level_value}`}
                      </p>
                      {c.department && (
                        <p>
                          <span className="text-slate-500">Dept:</span> {c.department}
                        </p>
                      )}
                    </div>

                    {/* Class Join Code Box */}
                    <div className="my-3 p-3 rounded-xl bg-black/40 border border-white/5 space-y-2">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-slate-400 font-medium flex items-center gap-1">
                          <KeyRound size={12} className="text-emerald-400" /> Class Join Code
                        </span>
                        <span className={`px-1.5 py-0.2 rounded text-[10px] font-semibold ${
                          c.join_code_enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'
                        }`}>
                          {c.join_code_enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <span className={`font-mono text-xs font-bold tracking-wider ${
                          c.join_code_enabled ? 'text-white' : 'text-slate-500 line-through'
                        }`}>
                          {c.join_code || '—'}
                        </span>
                        <div className="flex items-center gap-1">
                          {c.join_code && (
                            <button
                              onClick={() => copyCohortCode(c.id, c.join_code)}
                              className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                              title="Copy class code"
                            >
                              {copiedCohortCodes[c.id] ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                            </button>
                          )}
                          <button
                            onClick={() => handleRegenerateCohortCode(c)}
                            disabled={regeneratingCohortId === c.id}
                            className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                            title="Regenerate class code"
                          >
                            <RefreshCw size={13} className={regeneratingCohortId === c.id ? 'animate-spin' : ''} />
                          </button>
                          <button
                            onClick={() => handleToggleCohortCode(c)}
                            disabled={togglingCohortId === c.id}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                              c.join_code_enabled
                                ? 'text-slate-400 hover:text-red-400 hover:bg-red-500/10'
                                : 'text-emerald-400 hover:bg-emerald-500/10'
                            }`}
                            title={c.join_code_enabled ? 'Disable class code' : 'Enable class code'}
                          >
                            {c.join_code_enabled ? 'Disable' : 'Enable'}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-white/5 flex items-center justify-end gap-2 mt-2">
                    <button
                      onClick={() => openEditClass(c)}
                      className="p-1.5 text-xs text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
                      title="Edit class"
                    >
                      <Edit2 size={14} />
                    </button>
                    {c.is_active && (
                      <button
                        onClick={() => handleDeactivateClass(c)}
                        className="p-1.5 text-xs text-red-400 hover:text-red-300 rounded-lg hover:bg-red-500/10 transition-colors"
                        title="Deactivate class"
                      >
                        <PowerOff size={14} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: JOIN REQUESTS */}
      {activeTab === 'requests' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-white">Pending Join Requests</h2>
              <p className="text-xs text-slate-400">Review and approve students who submitted your institution or class join code</p>
            </div>
            <button
              onClick={loadData}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
              title="Refresh"
            >
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-500 text-sm">
              <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              Loading requests...
            </div>
          ) : joinRequests.length === 0 ? (
            <div className="p-12 text-center rounded-2xl bg-white/[0.02] border border-white/10">
              <CheckCircle2 size={36} className="mx-auto text-emerald-500/40 mb-3" />
              <p className="text-sm text-slate-300 font-medium">All caught up!</p>
              <p className="text-xs text-slate-500 mt-1">There are no pending join requests for your institution.</p>
            </div>
          ) : (
            <div className="rounded-2xl bg-white/[0.02] border border-white/10 overflow-hidden">
              <div className="divide-y divide-white/5">
                {joinRequests.map((req) => (
                  <div key={req.id} className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-white/[0.01] transition-colors">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-white text-sm">
                          {req.user_full_name || req.user_username}
                        </p>
                        <span className="text-xs text-slate-500">(@{req.user_username})</span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">{req.user_email}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                        {req.requested_cohort_name ? (
                          <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-medium flex items-center gap-1">
                            <Layers size={11} /> Requested: {req.requested_cohort_name}
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/10">
                            Institution-wide Code
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <Clock size={11} /> {new Date(req.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-auto">
                      <button
                        onClick={() => handleDecide(req.id, 'reject')}
                        disabled={decidingId === req.id}
                        className="px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-300 font-medium text-xs rounded-lg transition-colors flex items-center gap-1"
                      >
                        <XCircle size={14} /> Reject
                      </button>
                      <button
                        onClick={() => {
                          setApprovingReq(req);
                          setAssignedCohortId(req.requested_cohort_id || (cohorts[0]?.id || ''));
                        }}
                        disabled={decidingId === req.id}
                        className="px-3.5 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-lg transition-colors flex items-center gap-1"
                      >
                        <CheckCircle2 size={14} /> Approve...
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODAL: Create / Edit Class */}
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
                    Class Name * (e.g. &quot;Grade 9-A&quot; or &quot;SE Computer&quot;)
                  </label>
                  <input
                    type="text"
                    required
                    value={classForm.name}
                    onChange={(e) => setClassForm({ ...classForm, name: e.target.value })}
                    placeholder="e.g. SE Computer Division A"
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
                      className="w-full px-3 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-xs focus:outline-none focus:border-emerald-500"
                    >
                      <option value="college_year">College Year</option>
                      <option value="grade">School Grade</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Level Value (e.g. 9, SE)
                    </label>
                    <input
                      type="text"
                      required
                      value={classForm.level_value}
                      onChange={(e) => setClassForm({ ...classForm, level_value: e.target.value })}
                      placeholder="e.g. SE, 10"
                      className="w-full px-3 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-xs focus:outline-none focus:border-emerald-500"
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

      {/* MODAL: Approve Join Request with Class Assignment */}
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
