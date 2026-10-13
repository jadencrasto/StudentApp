import { useState } from 'react';
import { motion } from 'framer-motion';
import { School, Clock, CheckCircle2, AlertCircle, ArrowRight, RefreshCw, KeyRound } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../../hooks/useAuth';
import { submitJoin } from '../../api/auth';

export default function JoinCard({ className = '' }) {
  const { user, role, institution, cohort, join_request_status, refreshUser } = useAuth();
  const [joinCode, setJoinCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (role !== 'student') {
    return null;
  }

  const status = join_request_status || (institution ? 'approved' : 'none');

  async function handleJoin(e) {
    e.preventDefault();
    const cleanCode = joinCode.trim().toUpperCase();
    if (!cleanCode) {
      setError('Please enter a join code');
      return;
    }

    setError('');
    setLoading(true);

    try {
      await submitJoin({ join_code: cleanCode });
      toast.success('Join request submitted! Waiting for approval.');
      setJoinCode('');
      await refreshUser();
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 429) {
        setError('Too many join attempts. Rate limit reached (10 per hour). Please try again later.');
      } else if (status === 400 && detail?.toLowerCase().includes('invalid join code')) {
        setError('Invalid join code. Please check with your teacher or institution admin.');
      } else {
        setError(detail || 'Could not submit join request. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  // 1. APPROVED STATE
  if (status === 'approved' && institution) {
    return (
      <div className={`p-6 rounded-2xl bg-white/[0.03] border border-emerald-500/30 backdrop-blur-sm ${className}`}>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0 text-emerald-400">
            <CheckCircle2 size={24} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Enrolled
              </span>
              <span className="text-xs text-slate-500 capitalize">{institution.type}</span>
            </div>
            <h3 className="text-lg font-semibold text-white mt-1 truncate">{institution.name}</h3>
            {institution.location && (
              <p className="text-xs text-slate-400 mt-0.5">{institution.location}</p>
            )}
            {cohort && (
              <div className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-slate-200">
                <span className="text-slate-400">Class:</span>
                <span className="font-medium text-emerald-300">{cohort.name}</span>
                <span className="text-slate-500">({cohort.academic_year})</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 2. PENDING STATE
  if (status === 'pending') {
    return (
      <div className={`p-6 rounded-2xl bg-white/[0.03] border border-amber-500/30 backdrop-blur-sm ${className}`}>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0 text-amber-400">
            <Clock size={24} className="animate-pulse" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Pending Approval
              </span>
            </div>
            <h3 className="text-base font-semibold text-white mt-1">Waiting for Admin Approval</h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              Your join request was submitted to the institution administrators. Once approved, your class and official timetables will appear here automatically.
            </p>
            <button
              onClick={() => refreshUser()}
              className="mt-3 flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 transition-colors"
            >
              <RefreshCw size={13} /> Check Status
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 3. REJECTED OR NONE STATE
  return (
    <div className={`p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm ${className}`}>
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <KeyRound size={18} />
        </div>
        <div>
          <h3 className="text-base font-semibold text-white">Join with Institution or Class Code</h3>
          <p className="text-xs text-slate-400">Enter your institution or class code to access official academic courses</p>
        </div>
      </div>

      {status === 'rejected' && (
        <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-2.5 text-xs text-red-300">
          <AlertCircle size={16} className="flex-shrink-0 mt-0.5 text-red-400" />
          <div>
            <span className="font-medium">Previous request was not approved.</span> You can enter a valid code below to submit a new request.
          </div>
        </div>
      )}

      <form onSubmit={handleJoin} className="space-y-3">
        <div>
          <div className="relative">
            <input
              type="text"
              value={joinCode}
              onChange={(e) => {
                setJoinCode(e.target.value.toUpperCase());
                if (error) setError('');
              }}
              placeholder="e.g. 8A3F9K2X"
              maxLength={16}
              className="w-full px-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500/50 text-sm tracking-wider uppercase font-mono"
            />
            <button
              type="submit"
              disabled={loading || !joinCode.trim()}
              className="absolute right-1.5 top-1.5 bottom-1.5 px-4 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:hover:bg-emerald-500 text-black font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  Join <ArrowRight size={13} />
                </>
              )}
            </button>
          </div>
          {error && (
            <p className="text-xs text-red-400 mt-2 flex items-center gap-1.5">
              <AlertCircle size={13} /> {error}
            </p>
          )}
        </div>
        <p className="text-[11px] text-slate-500">
          Joining an institution is optional. You can always study independently or join anytime later.
        </p>
      </form>
    </div>
  );
}
