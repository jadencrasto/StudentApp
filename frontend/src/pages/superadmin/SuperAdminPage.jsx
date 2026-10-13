import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Building2, School, GraduationCap, Plus, Copy, Check,
  UserPlus, ShieldCheck, PowerOff, AlertCircle, RefreshCw, X, MapPin, KeyRound,
  Users, CheckCircle2, RotateCcw, AlertTriangle, Layers
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { institutionsAPI } from '../../api/client';

export default function SuperAdminPage() {
  const [activeTab, setActiveTab] = useState('institutions'); // 'institutions' | 'admins'

  // Institutions state
  const [institutions, setInstitutions] = useState([]);
  const [loadingInsts, setLoadingInsts] = useState(true);
  const [errorInsts, setErrorInsts] = useState('');

  // Admins state
  const [admins, setAdmins] = useState([]);
  const [loadingAdmins, setLoadingAdmins] = useState(false);
  const [errorAdmins, setErrorAdmins] = useState('');

  // Modals
  const [showCreateInst, setShowCreateInst] = useState(false);
  const [showCreateAdmin, setShowCreateAdmin] = useState(false);
  const [selectedInstForAdmin, setSelectedInstForAdmin] = useState('');

  // Reset password single-view state
  const [resetPasswordModal, setResetPasswordModal] = useState(null); // { adminName, email, tempPassword }
  const [copiedResetPassword, setCopiedResetPassword] = useState(false);

  // Forms
  const [instForm, setInstForm] = useState({ name: '', type: 'college', location: '' });
  const [adminForm, setAdminForm] = useState({ fullName: '', username: '', email: '', password: '' });
  const [submitting, setSubmitting] = useState(false);
  const [copiedCode, setCopiedCode] = useState(null);

  // Newly created institution modal display
  const [createdInst, setCreatedInst] = useState(null);

  async function loadInstitutions() {
    setLoadingInsts(true);
    setErrorInsts('');
    try {
      const res = await institutionsAPI.listInstitutionsWithCounts();
      setInstitutions(res.data);
    } catch (err) {
      setErrorInsts(err.response?.data?.detail || 'Failed to load institutions');
    } finally {
      setLoadingInsts(false);
    }
  }

  async function loadAdmins() {
    setLoadingAdmins(true);
    setErrorAdmins('');
    try {
      const res = await institutionsAPI.listAdmins();
      setAdmins(res.data);
    } catch (err) {
      setErrorAdmins(err.response?.data?.detail || 'Failed to load administrators');
    } finally {
      setLoadingAdmins(false);
    }
  }

  useEffect(() => {
    loadInstitutions();
    loadAdmins();
  }, []);

  function copyToClipboard(code) {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    toast.success(`Copied join code: ${code}`);
    setTimeout(() => setCopiedCode(null), 2000);
  }

  function copyTempPassword(pwd) {
    navigator.clipboard.writeText(pwd);
    setCopiedResetPassword(true);
    toast.success('Temporary password copied to clipboard!');
    setTimeout(() => setCopiedResetPassword(false), 2000);
  }

  async function handleCreateInstitution(e) {
    e.preventDefault();
    if (!instForm.name.trim()) return;

    setSubmitting(true);
    try {
      const res = await institutionsAPI.createInstitution({
        name: instForm.name.trim(),
        type: instForm.type,
        location: instForm.location.trim() || undefined,
      });
      toast.success('Institution created successfully!');
      setCreatedInst(res.data);
      setShowCreateInst(false);
      setInstForm({ name: '', type: 'college', location: '' });
      await loadInstitutions();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create institution');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreateAdmin(e) {
    e.preventDefault();
    if (!selectedInstForAdmin) {
      toast.error('Please select an institution');
      return;
    }

    setSubmitting(true);
    try {
      await institutionsAPI.createAdmin(selectedInstForAdmin, {
        email: adminForm.email.trim().toLowerCase(),
        username: adminForm.username.trim().toLowerCase(),
        full_name: adminForm.fullName.trim() || undefined,
        password: adminForm.password,
      });
      toast.success('Administrator created! Temporary password set.');
      setShowCreateAdmin(false);
      setAdminForm({ fullName: '', username: '', email: '', password: '' });
      setSelectedInstForAdmin('');
      await Promise.all([loadInstitutions(), loadAdmins()]);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create administrator');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivateInst(inst) {
    if (!window.confirm(`Are you sure you want to deactivate "${inst.name}"? Active users will no longer be able to use its join code.`)) {
      return;
    }

    try {
      await institutionsAPI.deactivateInstitution(inst.id);
      toast.success(`Deactivated ${inst.name}`);
      await loadInstitutions();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to deactivate institution');
    }
  }

  async function handleDeactivateAdmin(admin) {
    if (!window.confirm(`Deactivate administrator "${admin.full_name || admin.username}"? They will lose access immediately.`)) {
      return;
    }

    try {
      await institutionsAPI.deactivateAdmin(admin.id);
      toast.success(`Administrator deactivated`);
      await loadAdmins();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to deactivate administrator');
    }
  }

  async function handleReactivateAdmin(admin) {
    try {
      await institutionsAPI.reactivateAdmin(admin.id);
      toast.success(`Administrator reactivated`);
      await loadAdmins();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reactivate administrator');
    }
  }

  async function handleResetPassword(admin) {
    if (!window.confirm(`Reset password for administrator "${admin.full_name || admin.username}"? A temporary password will be generated and shown ONCE.`)) {
      return;
    }

    try {
      const res = await institutionsAPI.resetAdminPassword(admin.id);
      setResetPasswordModal({
        adminName: admin.full_name || admin.username,
        email: admin.email,
        tempPassword: res.data.temporary_password,
      });
      await loadAdmins();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reset password');
    }
  }

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <ShieldCheck size={18} />
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Super Administrator</h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Global management of academic institutions, join codes, and administrators.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowCreateAdmin(true)}
            className="px-3.5 py-2 bg-white/5 hover:bg-white/10 text-white border border-white/10 font-medium text-xs rounded-xl flex items-center gap-2 transition-colors"
          >
            <UserPlus size={15} /> Add Administrator
          </button>
          <button
            onClick={() => setShowCreateInst(true)}
            className="px-3.5 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl flex items-center gap-2 transition-colors shadow-lg shadow-emerald-500/10"
          >
            <Plus size={15} /> New Institution
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-3 border-b border-white/10 mb-6">
        <button
          onClick={() => setActiveTab('institutions')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'institutions'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Building2 size={16} />
          <span>Institutions</span>
          <span className="px-1.5 py-0.5 rounded text-[11px] bg-white/10 text-slate-300">
            {institutions.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('admins')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'admins'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Users size={16} />
          <span>Admins</span>
          <span className="px-1.5 py-0.5 rounded text-[11px] bg-white/10 text-slate-300">
            {admins.length}
          </span>
        </button>
      </div>

      {/* TAB 1: INSTITUTIONS */}
      {activeTab === 'institutions' && (
        <div className="space-y-6">
          {/* Stats Overview */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10">
              <p className="text-xs font-medium text-slate-400">Total Institutions</p>
              <p className="text-2xl font-bold text-white mt-1">{institutions.length}</p>
            </div>
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10">
              <p className="text-xs font-medium text-slate-400">Active</p>
              <p className="text-2xl font-bold text-emerald-400 mt-1">
                {institutions.filter(i => i.is_active).length}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10">
              <p className="text-xs font-medium text-slate-400">Colleges</p>
              <p className="text-2xl font-bold text-blue-400 mt-1">
                {institutions.filter(i => i.type === 'college').length}
              </p>
            </div>
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10">
              <p className="text-xs font-medium text-slate-400">Schools</p>
              <p className="text-2xl font-bold text-amber-400 mt-1">
                {institutions.filter(i => i.type === 'school').length}
              </p>
            </div>
          </div>

          {/* Institutions Directory Table */}
          <div className="rounded-2xl bg-white/[0.02] border border-white/10 overflow-hidden">
            <div className="p-5 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Building2 size={18} className="text-emerald-400" />
                <h2 className="text-base font-semibold text-white">Institutions Directory</h2>
              </div>
              <button
                onClick={loadInstitutions}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
                title="Refresh"
              >
                <RefreshCw size={15} className={loadingInsts ? 'animate-spin' : ''} />
              </button>
            </div>

            {errorInsts && (
              <div className="p-4 bg-red-500/10 border-b border-red-500/20 text-xs text-red-300 flex items-center gap-2">
                <AlertCircle size={15} /> {errorInsts}
              </div>
            )}

            {loadingInsts ? (
              <div className="p-12 text-center text-slate-500 text-sm">
                <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                Loading institutions...
              </div>
            ) : institutions.length === 0 ? (
              <div className="p-12 text-center">
                <Building2 size={36} className="mx-auto text-slate-600 mb-3" />
                <p className="text-sm text-slate-300 font-medium">No institutions registered yet</p>
                <p className="text-xs text-slate-500 mt-1">Create an institution to issue join codes and assign administrators.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/[0.02] text-xs text-slate-400 font-medium border-b border-white/10">
                    <tr>
                      <th className="py-3 px-5">Institution</th>
                      <th className="py-3 px-5">Type</th>
                      <th className="py-3 px-5">Location</th>
                      <th className="py-3 px-5">Counts</th>
                      <th className="py-3 px-5">Join Code</th>
                      <th className="py-3 px-5">Status</th>
                      <th className="py-3 px-5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {institutions.map((inst) => (
                      <tr key={inst.id} className="hover:bg-white/[0.01] transition-colors">
                        <td className="py-3.5 px-5">
                          <p className="font-semibold text-white">{inst.name}</p>
                          <p className="text-[11px] text-slate-500 font-mono">{inst.id.slice(0, 8)}...</p>
                        </td>
                        <td className="py-3.5 px-5">
                          <span className="capitalize text-xs px-2.5 py-1 rounded-md bg-white/5 border border-white/10 text-slate-300">
                            {inst.type}
                          </span>
                        </td>
                        <td className="py-3.5 px-5 text-slate-300 text-xs">
                          {inst.location ? (
                            <span className="flex items-center gap-1.5">
                              <MapPin size={12} className="text-slate-500" /> {inst.location}
                            </span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="py-3.5 px-5 text-xs text-slate-300">
                          <div className="flex items-center gap-3">
                            <span title="Admins" className="flex items-center gap-1 text-slate-300">
                              <span className="text-slate-500">Admins:</span> <span className="font-semibold text-white">{inst.admin_count ?? 0}</span>
                            </span>
                            <span className="text-slate-600">|</span>
                            <span title="Classes" className="flex items-center gap-1 text-slate-300">
                              <span className="text-slate-500">Classes:</span> <span className="font-semibold text-white">{inst.class_count ?? 0}</span>
                            </span>
                            <span className="text-slate-600">|</span>
                            <span title="Students" className="flex items-center gap-1 text-slate-300">
                              <span className="text-slate-500">Students:</span> <span className="font-semibold text-emerald-400">{inst.student_count ?? 0}</span>
                            </span>
                          </div>
                        </td>
                        <td className="py-3.5 px-5">
                          <div className="inline-flex items-center gap-2 bg-black/50 border border-white/10 px-2.5 py-1 rounded-lg">
                            <span className="font-mono text-emerald-400 font-bold tracking-wider text-xs">
                              {inst.join_code}
                            </span>
                            <button
                              onClick={() => copyToClipboard(inst.join_code)}
                              className="text-slate-400 hover:text-white transition-colors"
                              title="Copy join code"
                            >
                              {copiedCode === inst.join_code ? (
                                <Check size={13} className="text-emerald-400" />
                              ) : (
                                <Copy size={13} />
                              )}
                            </button>
                          </div>
                        </td>
                        <td className="py-3.5 px-5">
                          {inst.is_active ? (
                            <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                              <span className="w-1.5 h-1.5 rounded-full bg-slate-500" /> Inactive
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-5 text-right">
                          {inst.is_active && (
                            <button
                              onClick={() => handleDeactivateInst(inst)}
                              className="px-2.5 py-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors inline-flex items-center gap-1.5"
                              title="Deactivate institution"
                            >
                              <PowerOff size={13} /> Deactivate
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: ADMINS */}
      {activeTab === 'admins' && (
        <div className="space-y-6">
          <div className="rounded-2xl bg-white/[0.02] border border-white/10 overflow-hidden">
            <div className="p-5 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users size={18} className="text-emerald-400" />
                <div>
                  <h2 className="text-base font-semibold text-white">Institution Administrators</h2>
                  <p className="text-xs text-slate-400">All registered institution admin accounts across the platform</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowCreateAdmin(true)}
                  className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl flex items-center gap-1.5 transition-colors"
                >
                  <Plus size={14} /> Add Administrator
                </button>
                <button
                  onClick={loadAdmins}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
                  title="Refresh"
                >
                  <RefreshCw size={15} className={loadingAdmins ? 'animate-spin' : ''} />
                </button>
              </div>
            </div>

            {errorAdmins && (
              <div className="p-4 bg-red-500/10 border-b border-red-500/20 text-xs text-red-300 flex items-center gap-2">
                <AlertCircle size={15} /> {errorAdmins}
              </div>
            )}

            {loadingAdmins ? (
              <div className="p-12 text-center text-slate-500 text-sm">
                <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                Loading administrators...
              </div>
            ) : admins.length === 0 ? (
              <div className="p-12 text-center">
                <Users size={36} className="mx-auto text-slate-600 mb-3" />
                <p className="text-sm text-slate-300 font-medium">No institution administrators created yet</p>
                <p className="text-xs text-slate-500 mt-1">Click &quot;Add Administrator&quot; to assign an admin to an active institution.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/[0.02] text-xs text-slate-400 font-medium border-b border-white/10">
                    <tr>
                      <th className="py-3 px-5">Name / Username</th>
                      <th className="py-3 px-5">Email</th>
                      <th className="py-3 px-5">Institution</th>
                      <th className="py-3 px-5">Status</th>
                      <th className="py-3 px-5">Created Date</th>
                      <th className="py-3 px-5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {admins.map((adm) => (
                      <tr key={adm.id} className="hover:bg-white/[0.01] transition-colors">
                        <td className="py-3.5 px-5">
                          <p className="font-semibold text-white">{adm.full_name || adm.username}</p>
                          <p className="text-[11px] text-slate-500">@{adm.username}</p>
                        </td>
                        <td className="py-3.5 px-5 text-xs text-slate-300 font-mono">
                          {adm.email}
                        </td>
                        <td className="py-3.5 px-5 text-xs text-slate-300">
                          {adm.institution_name ? (
                            <span className="flex items-center gap-1.5 font-medium text-white">
                              <Building2 size={13} className="text-emerald-400" /> {adm.institution_name}
                            </span>
                          ) : (
                            <span className="text-slate-500">Unassigned</span>
                          )}
                        </td>
                        <td className="py-3.5 px-5">
                          {adm.is_active ? (
                            <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                              <span className="w-1.5 h-1.5 rounded-full bg-slate-500" /> Inactive
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-5 text-xs text-slate-400">
                          {adm.created_at ? new Date(adm.created_at).toLocaleDateString() : '—'}
                        </td>
                        <td className="py-3.5 px-5 text-right">
                          <div className="inline-flex items-center gap-2">
                            <button
                              onClick={() => handleResetPassword(adm)}
                              className="px-2.5 py-1 text-xs text-amber-300 hover:text-amber-200 hover:bg-amber-500/10 rounded-lg transition-colors inline-flex items-center gap-1"
                              title="Reset Password"
                            >
                              <RotateCcw size={13} /> Reset Pwd
                            </button>
                            {adm.is_active ? (
                              <button
                                onClick={() => handleDeactivateAdmin(adm)}
                                className="px-2.5 py-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors inline-flex items-center gap-1"
                                title="Deactivate Administrator"
                              >
                                <PowerOff size={13} /> Deactivate
                              </button>
                            ) : (
                              <button
                                onClick={() => handleReactivateAdmin(adm)}
                                className="px-2.5 py-1 text-xs text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 rounded-lg transition-colors inline-flex items-center gap-1"
                                title="Reactivate Administrator"
                              >
                                <CheckCircle2 size={13} /> Reactivate
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODAL: Reset Password (SHOWN ONCE) */}
      <AnimatePresence>
        {resetPasswordModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-amber-500/40 rounded-2xl shadow-2xl relative text-center"
            >
              <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mx-auto mb-4">
                <KeyRound size={26} />
              </div>
              <h3 className="text-lg font-bold text-white">Temporary Password Generated</h3>
              <p className="text-xs text-slate-300 mt-1">
                Password reset for <span className="font-semibold text-white">{resetPasswordModal.adminName}</span> ({resetPasswordModal.email})
              </p>

              {/* Warning Banner */}
              <div className="my-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-left flex items-start gap-2.5">
                <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
                <p className="text-[11px] text-amber-200 leading-relaxed font-medium">
                  <strong>Important:</strong> This temporary password is displayed <u>ONCE</u> and cannot be retrieved again. Copy it now and share it securely with the administrator.
                </p>
              </div>

              {/* Code Box */}
              <div className="my-4 p-4 bg-black/60 border border-white/10 rounded-xl flex items-center justify-between">
                <span className="font-mono text-base font-bold tracking-wider text-emerald-400 select-all">
                  {resetPasswordModal.tempPassword}
                </span>
                <button
                  onClick={() => copyTempPassword(resetPasswordModal.tempPassword)}
                  className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
                >
                  {copiedResetPassword ? <Check size={13} /> : <Copy size={13} />}
                  {copiedResetPassword ? 'Copied' : 'Copy'}
                </button>
              </div>

              <p className="text-[11px] text-slate-400 mb-5 leading-relaxed">
                The administrator will be prompted to choose a new password upon their next login.
              </p>

              <button
                onClick={() => setResetPasswordModal(null)}
                className="w-full py-2.5 bg-white/10 hover:bg-white/15 text-white font-medium text-xs rounded-xl transition-colors"
              >
                I Have Copied the Password
              </button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* MODAL 1: Create Institution */}
      <AnimatePresence>
        {showCreateInst && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setShowCreateInst(false)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <div className="flex items-center gap-2.5 mb-5">
                <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <Building2 size={20} />
                </div>
                <h3 className="text-lg font-bold text-white">Create New Institution</h3>
              </div>

              <form onSubmit={handleCreateInstitution} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Institution Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={instForm.name}
                    onChange={(e) => setInstForm({ ...instForm, name: e.target.value })}
                    placeholder="e.g. Apex Engineering College"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Type *
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => setInstForm({ ...instForm, type: 'college' })}
                      className={`py-2 px-3 rounded-xl border text-xs font-medium flex items-center justify-center gap-2 ${
                        instForm.type === 'college'
                          ? 'bg-emerald-500/15 border-emerald-500 text-emerald-300'
                          : 'bg-black/40 border-white/10 text-slate-400'
                      }`}
                    >
                      <GraduationCap size={15} /> College
                    </button>
                    <button
                      type="button"
                      onClick={() => setInstForm({ ...instForm, type: 'school' })}
                      className={`py-2 px-3 rounded-xl border text-xs font-medium flex items-center justify-center gap-2 ${
                        instForm.type === 'school'
                          ? 'bg-emerald-500/15 border-emerald-500 text-emerald-300'
                          : 'bg-black/40 border-white/10 text-slate-400'
                      }`}
                    >
                      <School size={15} /> School
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    City / Location (Optional)
                  </label>
                  <input
                    type="text"
                    value={instForm.location}
                    onChange={(e) => setInstForm({ ...instForm, location: e.target.value })}
                    placeholder="e.g. Mumbai, Maharashtra"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowCreateInst(false)}
                    className="px-4 py-2 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold text-xs rounded-xl transition-colors"
                  >
                    {submitting ? 'Creating...' : 'Create & Generate Code'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* MODAL 2: Newly Created Institution Join Code Modal */}
      <AnimatePresence>
        {createdInst && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-emerald-500/40 rounded-2xl shadow-2xl relative text-center"
            >
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mx-auto mb-4">
                <KeyRound size={26} />
              </div>
              <h3 className="text-lg font-bold text-white">Institution Created!</h3>
              <p className="text-xs text-slate-400 mt-1">
                &quot;{createdInst.name}&quot; has been created with the following official join code:
              </p>

              <div className="my-5 p-4 bg-black/60 border border-emerald-500/30 rounded-xl flex items-center justify-between">
                <span className="font-mono text-xl font-bold tracking-widest text-emerald-400">
                  {createdInst.join_code}
                </span>
                <button
                  onClick={() => copyToClipboard(createdInst.join_code)}
                  className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
                >
                  <Copy size={13} /> Copy Code
                </button>
              </div>

              <p className="text-[11px] text-slate-500 mb-5 leading-relaxed">
                Provide this join code to teachers and students. You can now create an administrator account for this institution.
              </p>

              <button
                onClick={() => setCreatedInst(null)}
                className="w-full py-2.5 bg-white/10 hover:bg-white/15 text-white font-medium text-xs rounded-xl transition-colors"
              >
                Close
              </button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* MODAL 3: Create Institution Administrator */}
      <AnimatePresence>
        {showCreateAdmin && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md p-6 bg-slate-900 border border-white/10 rounded-2xl shadow-2xl relative"
            >
              <button
                onClick={() => setShowCreateAdmin(false)}
                className="absolute top-4 right-4 text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>

              <div className="flex items-center gap-2.5 mb-5">
                <div className="w-9 h-9 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                  <UserPlus size={20} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white">Create Administrator</h3>
                  <p className="text-xs text-slate-400">Assign an administrator to manage an institution</p>
                </div>
              </div>

              <form onSubmit={handleCreateAdmin} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Institution *
                  </label>
                  <select
                    required
                    value={selectedInstForAdmin}
                    onChange={(e) => setSelectedInstForAdmin(e.target.value)}
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">Select an institution...</option>
                    {institutions.filter(i => i.is_active).map((inst) => (
                      <option key={inst.id} value={inst.id}>
                        {inst.name} ({inst.type})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={adminForm.fullName}
                    onChange={(e) => setAdminForm({ ...adminForm, fullName: e.target.value })}
                    placeholder="e.g. Dr. Rajesh Sharma"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Username *
                  </label>
                  <input
                    type="text"
                    required
                    value={adminForm.username}
                    onChange={(e) => setAdminForm({ ...adminForm, username: e.target.value })}
                    placeholder="e.g. principal_apex"
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
                    value={adminForm.email}
                    onChange={(e) => setAdminForm({ ...adminForm, email: e.target.value })}
                    placeholder="e.g. admin@apex.edu"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Temporary Password * (8+ chars, letters & digits)
                  </label>
                  <input
                    type="password"
                    required
                    minLength={8}
                    value={adminForm.password}
                    onChange={(e) => setAdminForm({ ...adminForm, password: e.target.value })}
                    placeholder="TemporaryPassword123!"
                    className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                  <p className="text-[11px] text-amber-400/90 mt-1.5 flex items-center gap-1">
                    <ShieldCheck size={12} /> The administrator must change this password on first login.
                  </p>
                </div>

                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowCreateAdmin(false)}
                    className="px-4 py-2 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-5 py-2.5 bg-blue-500 hover:bg-blue-400 disabled:opacity-50 text-white font-semibold text-xs rounded-xl transition-colors"
                  >
                    {submitting ? 'Creating Admin...' : 'Create Admin'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
