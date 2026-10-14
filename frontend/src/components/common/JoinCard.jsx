import { useState } from 'react';
import { motion } from 'framer-motion';
import { School, Clock, CheckCircle2, AlertCircle, ArrowRight, RefreshCw, KeyRound, Layers } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../../hooks/useAuth';
import { submitJoin, submitClassJoin } from '../../api/auth';

export default function JoinCard({ className = '' }) {
  const {
    user,
    role,
    institution,
    cohort,
    join_request_status,
    join_request_type,
    join_requested_cohort_name,
    refreshUser,
  } = useAuth();

  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (role !== 'student') {
    return null;
  }

  // ── Determine Student State (States 1 - 7) ──────────────────────────
  // State 7: Fully joined (institution + class)
  const isFullyJoined = !!institution && !!cohort;

  // State 4, 5, 6: In institution, but not in a class yet
  const isInInstitutionNoClass = !!institution && !cohort;

  // Class request pending (State 5) or rejected (State 6)
  const isClassPending = isInInstitutionNoClass && join_request_type === 'class' && join_request_status === 'pending';
  const isClassRejected = isInInstitutionNoClass && join_request_type === 'class' && join_request_status === 'rejected';

  // State 2: Institution request pending
  const isInstitutionPending = !institution && join_request_type === 'institution' && join_request_status === 'pending';

  // State 3: Institution request rejected
  const isInstitutionRejected = !institution && join_request_type === 'institution' && join_request_status === 'rejected';

  // ── Submit Step 1: Institution Code ─────────────────────────────────
  async function handleInstitutionJoin(e) {
    e.preventDefault();
    const cleanCode = code.trim().toUpperCase();
    if (!cleanCode) {
      setError('Please enter your institution join code');
      return;
    }

    setError('');
    setLoading(true);

    try {
      await submitJoin({ join_code: cleanCode });
      toast.success('Institution join request submitted! Awaiting approval.');
      setCode('');
      await refreshUser();
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 429) {
        setError('Too many join attempts. Rate limit reached (10 per hour). Please try again later.');
      } else if (status === 400 && detail?.toLowerCase().includes('invalid join code')) {
        setError('Invalid institution code. Please check with your administrator.');
      } else {
        setError(detail || 'Could not submit join request. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  // ── Submit Step 2: Class Code ───────────────────────────────────────
  async function handleClassJoin(e) {
    e.preventDefault();
    const cleanCode = code.trim().toUpperCase();
    if (!cleanCode) {
      setError('Please enter your class join code');
      return;
    }

    setError('');
    setLoading(true);

    try {
      await submitClassJoin({ join_code: cleanCode });
      toast.success('Class join request submitted! Awaiting approval.');
      setCode('');
      await refreshUser();
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 429) {
        setError('Too many attempts. Rate limit reached (10 per hour). Please try again later.');
      } else if (status === 400 && detail?.toLowerCase().includes('invalid class code')) {
        setError('Invalid class code. Please check with your teacher or administrator.');
      } else {
        setError(detail || 'Could not submit class join request. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  // ── STATE 7: FULLY JOINED (Institution + Class) ─────────────────────
  if (isFullyJoined) {
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
            <div className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-slate-200">
              <span className="text-emerald-400 font-medium">Class:</span>
              <span className="font-semibold text-white">{cohort.name}</span>
              <span className="text-slate-400">({cohort.academic_year})</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── STATE 5: CLASS REQUEST PENDING ──────────────────────────────────
  if (isClassPending) {
    return (
      <div className={`p-6 rounded-2xl bg-white/[0.03] border border-amber-500/30 backdrop-blur-sm ${className}`}>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0 text-amber-400">
            <Clock size={24} className="animate-pulse" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {institution.name}
              </span>
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Class Approval Pending
              </span>
            </div>
            <h3 className="text-base font-semibold text-white mt-1">
              Waiting for Class Approval{join_requested_cohort_name ? `: ${join_requested_cohort_name}` : ''}
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              Your class enrollment request is awaiting teacher or administrator approval. Once approved, your class timetable and tasks will be ready.
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

  // ── STATE 4 & 6: IN INSTITUTION, ENTER CLASS CODE ───────────────────
  if (isInInstitutionNoClass) {
    return (
      <div className={`p-6 rounded-2xl bg-white/[0.03] border border-emerald-500/20 backdrop-blur-sm ${className}`}>
        {/* Institution Badge */}
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <CheckCircle2 size={14} />
            </div>
            <span className="text-xs text-slate-300">
              Member of <strong className="text-white">{institution.name}</strong>
            </span>
          </div>
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            Step 2 of 2
          </span>
        </div>

        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <Layers size={18} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">Enter Your Class Code</h3>
            <p className="text-xs text-slate-400">Enter the code given by your teacher or class admin to enroll in your class.</p>
          </div>
        </div>

        {/* State 6: Class Rejected Banner */}
        {isClassRejected && (
          <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-2.5 text-xs text-red-300">
            <AlertCircle size={16} className="flex-shrink-0 mt-0.5 text-red-400" />
            <div>
              <span className="font-medium">Previous class request was not approved.</span> Please enter a valid class code below to submit a new request.
            </div>
          </div>
        )}

        <form onSubmit={handleClassJoin} className="space-y-3">
          <div>
            <div className="relative">
              <input
                type="text"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value.toUpperCase());
                  if (error) setError('');
                }}
                placeholder="e.g. 9B-2026 or CLASS CODE"
                maxLength={32}
                className="w-full px-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500/50 text-sm tracking-wider uppercase font-mono"
              />
              <button
                type="submit"
                disabled={loading || !code.trim()}
                className="absolute right-1.5 top-1.5 bottom-1.5 px-4 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:hover:bg-emerald-500 text-black font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors"
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    Join Class <ArrowRight size={13} />
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
            Ask your teacher or faculty for your official class code.
          </p>
        </form>
      </div>
    );
  }

  // ── STATE 2: INSTITUTION REQUEST PENDING ────────────────────────────
  if (isInstitutionPending) {
    return (
      <div className={`p-6 rounded-2xl bg-white/[0.03] border border-amber-500/30 backdrop-blur-sm ${className}`}>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0 text-amber-400">
            <Clock size={24} className="animate-pulse" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Step 1: Institution Pending
              </span>
            </div>
            <h3 className="text-base font-semibold text-white mt-1">Waiting for Institution Approval</h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              Your institution request was submitted to the administrators. Once approved, you can enter your class code to complete enrollment.
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

  // ── STATE 1 & 3: NO INSTITUTION (INDEPENDENT OR REJECTED) ───────────
  return (
    <div className={`p-6 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm ${className}`}>
      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <KeyRound size={18} />
        </div>
        <div>
          <h3 className="text-base font-semibold text-white">Join an Institution (Step 1)</h3>
          <p className="text-xs text-slate-400">Enter your institution join code to request membership</p>
        </div>
      </div>

      {/* State 3: Institution Rejected Banner */}
      {isInstitutionRejected && (
        <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-2.5 text-xs text-red-300">
          <AlertCircle size={16} className="flex-shrink-0 mt-0.5 text-red-400" />
          <div>
            <span className="font-medium">Previous request was not approved.</span> You can enter a valid institution code below to try again.
          </div>
        </div>
      )}

      <form onSubmit={handleInstitutionJoin} className="space-y-3">
        <div>
          <div className="relative">
            <input
              type="text"
              value={code}
              onChange={(e) => {
                setCode(e.target.value.toUpperCase());
                if (error) setError('');
              }}
              placeholder="e.g. 8A3F9K2X"
              maxLength={16}
              className="w-full px-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500/50 text-sm tracking-wider uppercase font-mono"
            />
            <button
              type="submit"
              disabled={loading || !code.trim()}
              className="absolute right-1.5 top-1.5 bottom-1.5 px-4 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:hover:bg-emerald-500 text-black font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-colors"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  Join Institution <ArrowRight size={13} />
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
