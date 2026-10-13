import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Lock, ShieldAlert, ArrowRight, LogOut, Check, X, AlertCircle } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../hooks/useAuth';
import { changePassword } from '../api/auth';
import { FallingPattern } from '../components/ui/falling-pattern';

export default function ChangePasswordPage() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Password rules validation
  const rules = useMemo(() => [
    { label: 'At least 8 characters', met: newPassword.length >= 8 },
    { label: 'Contains at least one letter', met: /[A-Za-z]/.test(newPassword) },
    { label: 'Contains at least one number', met: /\d/.test(newPassword) },
    { label: 'Passwords match', met: newPassword.length > 0 && newPassword === confirmPassword },
  ], [newPassword, confirmPassword]);

  const allRulesMet = rules.every(r => r.met);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!allRulesMet) {
      setError('Please satisfy all password security requirements');
      return;
    }

    setError('');
    setLoading(true);

    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });

      toast.success('Password updated successfully!');
      await refreshUser();

      // Redirect according to role
      const role = user?.role || 'student';
      if (role === 'super_admin') {
        navigate('/super-admin');
      } else if (role === 'admin') {
        navigate('/admin');
      } else {
        if (!user?.onboarding_completed) {
          navigate('/onboarding');
        } else {
          navigate('/dashboard');
        }
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update password');
      toast.error(err.response?.data?.detail || 'Password update failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative bg-black">
      {/* Background */}
      <div className="fixed inset-0 pointer-events-none" style={{ zIndex: 0 }}>
        <FallingPattern backgroundColor="#000000" className="h-full" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md relative z-10"
      >
        <div className="p-8 rounded-2xl bg-slate-900/90 border border-emerald-500/30 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <ShieldAlert size={26} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Change Password Required</h1>
              <p className="text-xs text-slate-400">Please choose a secure new password to continue</p>
            </div>
          </div>

          <p className="text-xs text-slate-400 mb-6 leading-relaxed bg-white/5 p-3 rounded-xl border border-white/10">
            For security, your temporary or initial password must be updated before you can access SAIS.
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 flex items-center gap-2 text-xs text-red-300">
              <AlertCircle size={15} className="flex-shrink-0 text-red-400" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Current Password
              </label>
              <div className="relative">
                <input
                  type="password"
                  required
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                New Password
              </label>
              <input
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Confirm New Password
              </label>
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repeat new password"
                className="w-full px-4 py-2.5 bg-black/50 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
              />
            </div>

            {/* Checklist */}
            <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1.5 text-[11px]">
              {rules.map((rule, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  {rule.met ? (
                    <Check size={13} className="text-emerald-400" />
                  ) : (
                    <X size={13} className="text-slate-500" />
                  )}
                  <span className={rule.met ? 'text-emerald-300' : 'text-slate-400'}>
                    {rule.label}
                  </span>
                </div>
              ))}
            </div>

            <button
              type="submit"
              disabled={loading || !allRulesMet || !currentPassword}
              className="w-full py-3 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:hover:bg-emerald-500 text-black font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2 mt-4"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-black border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  Set New Password & Continue <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-white/10 flex justify-center">
            <button
              onClick={() => logout()}
              className="text-xs text-slate-400 hover:text-red-400 flex items-center gap-1.5 transition-colors"
            >
              <LogOut size={13} /> Sign Out
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
