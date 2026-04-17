import { useMemo, useState } from 'react';
import { CheckCircle, Circle, Sun, Loader2, Check, Calendar } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { api } from '../../lib/api';

// ─── helpers ────────────────────────────────────────────────────────────────

/** Composite key that uniquely identifies one timetable slot. */
const slotKey = (subjectId, startTime) => `${subjectId}_${startTime}`;

/** Format an ISO timestamp as "8:07 AM" */
const fmtTime = (iso) => {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  } catch {
    return null;
  }
};

/** Return a human-readable day-off message based on JS weekday (0=Sun…6=Sat). */
const dayOffMessage = (weekday) => {
  if (weekday === 0) return "It's Sunday — no classes scheduled.";
  if (weekday === 6) return 'No classes this Saturday.';
  return 'No classes scheduled for today.';
};

// ─── component ──────────────────────────────────────────────────────────────

export default function MorningCheckin({ data }) {
  /** keyed by slotKey(subjectId, startTime) → { status, markedAt } */
  const [localMarked, setLocalMarked] = useState({});
  /** which slot key is currently being saved */
  const [markingId, setMarkingId] = useState(null);

  // ── Group consecutive same-subject classes (double lectures) ──────────────
  const groupedClasses = useMemo(() => {
    if (!data?.classes) return [];
    const grouped = [];
    let cur = null;

    data.classes.forEach((cls) => {
      if (
        cur &&
        cur.subject_id === cls.subject_id &&
        cur.end_time === cls.start_time
      ) {
        // Continuous extension — stretch the end time, keep the original start key
        cur.end_time = cls.end_time;
      } else {
        if (cur) grouped.push(cur);
        cur = { ...cls };
      }
    });
    if (cur) grouped.push(cur);
    return grouped;
  }, [data?.classes]);

  // ── Derived state ─────────────────────────────────────────────────────────

  const isClassMarked = (cls) => {
    const key = slotKey(cls.subject_id, cls.start_time);
    return cls.is_marked || !!localMarked[key];
  };

  const getMarkedAt = (cls) => {
    const key = slotKey(cls.subject_id, cls.start_time);
    // prefer local (just marked this session), fall back to server value
    return localMarked[key]?.markedAt ?? cls.marked_at ?? null;
  };

  const allMarked = groupedClasses.every(isClassMarked);
  const localMarkedCount = Object.keys(localMarked).length;
  const totalMarked = (data?.marked ?? 0) + localMarkedCount;

  // ── Mark single slot ──────────────────────────────────────────────────────

  const handleMark = async (cls, status) => {
    const key = slotKey(cls.subject_id, cls.start_time);
    setMarkingId(key);
    const markedAt = new Date().toISOString();
    try {
      const todayDate = markedAt.split('T')[0];
      await api.post('/attendance/mark', {
        subject_id: cls.subject_id,
        start_time: cls.start_time,
        end_time:   cls.end_time,
        date:       todayDate,
        status,
        marked_at:  markedAt,
      });
      setLocalMarked((prev) => ({
        ...prev,
        [key]: { status, markedAt },
      }));
      toast.success('Attendance marked!');
    } catch {
      toast.error('Failed to mark attendance.');
    } finally {
      setMarkingId(null);
    }
  };

  // ── Mark all remaining as present ─────────────────────────────────────────

  const handleMarkAllPresent = async () => {
    const unmarked = groupedClasses.filter((g) => !isClassMarked(g));
    if (!unmarked.length) return;

    const markedAt = new Date().toISOString();
    const todayDate = markedAt.split('T')[0];

    const promises = unmarked.map((g) =>
      api
        .post('/attendance/mark', {
          subject_id: g.subject_id,
          start_time: g.start_time,
          end_time:   g.end_time,
          date:       todayDate,
          status:     'present',
          marked_at:  markedAt,
        })
        .then(() => ({ key: slotKey(g.subject_id, g.start_time), markedAt }))
    );

    toast
      .promise(Promise.all(promises), {
        loading: 'Marking all remaining as present…',
        success: 'All set! Attendance marked.',
        error:   'Failed to mark all attendance.',
      })
      .then((results) => {
        setLocalMarked((prev) => {
          const next = { ...prev };
          results.forEach(({ key, markedAt: ts }) => {
            next[key] = { status: 'present', markedAt: ts };
          });
          return next;
        });
      });
  };

  // ── Empty-state (Feature 3) ───────────────────────────────────────────────

  const isEmpty = !data?.classes?.length;

  if (isEmpty) {
    const weekday = new Date().getDay(); // 0=Sun, 6=Sat
    const message = dayOffMessage(weekday);

    return (
      <div className="relative overflow-hidden bg-gradient-to-r from-emerald-400/10 via-teal-400/10 to-emerald-400/10 backdrop-blur-md border border-emerald-400/30 rounded-2xl p-5 mb-6">
        <div className="absolute inset-0 bg-gradient-to-r from-emerald-400/5 to-teal-400/5 blur-2xl" />

        <div className="relative flex items-start gap-4">
          <div className="flex-shrink-0 w-11 h-11 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-400/20">
            <Sun size={22} className="text-slate-900" />
          </div>

          <div className="flex-1 min-w-0">
            <h3 className="text-white font-semibold text-lg">Morning Check-in</h3>
            <p className="text-emerald-100/80 text-sm mb-4">No classes today</p>

            {/* Empty-state card */}
            <div className="flex flex-col items-center gap-3 py-6 px-4 bg-slate-900/40 backdrop-blur-sm rounded-lg border border-slate-800/50 text-center">
              <span className="text-3xl">☀️</span>
              <div>
                <p className="text-white font-medium text-sm">No classes today</p>
                <p className="text-emerald-300 text-sm mt-0.5">Enjoy your day off!</p>
              </div>
              <div className="flex items-center gap-2 mt-1 text-slate-400 text-xs">
                <Calendar size={13} />
                <span>{message}</span>
              </div>
              <p className="text-slate-500 text-xs mt-1">
                Check your timetable for upcoming classes.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Normal (non-empty) render ─────────────────────────────────────────────

  return (
    <div className="relative overflow-hidden bg-gradient-to-r from-emerald-400/10 via-teal-400/10 to-emerald-400/10 backdrop-blur-md border border-emerald-400/30 rounded-2xl p-5 mb-6">
      <div className="absolute inset-0 bg-gradient-to-r from-emerald-400/5 to-teal-400/5 blur-2xl" />

      <div className="relative flex items-start gap-4">
        <div className="flex-shrink-0 w-11 h-11 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-400/20">
          <Sun size={22} className="text-slate-900" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex justify-between items-start mb-1">
            <h3 className="text-white font-semibold text-lg">Morning Check-in</h3>
            {!allMarked && (
              <button
                onClick={handleMarkAllPresent}
                className="text-xs font-semibold px-4 py-2 min-h-[44px] bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 hover:text-emerald-200 transition-colors rounded-full flex items-center gap-1.5 border border-emerald-500/20"
              >
                <Check size={14} />
                Mark all Present
              </button>
            )}
          </div>

          <p className="text-emerald-100/80 text-sm mb-4">
            You have {data.total} class{data.total !== 1 ? 'es' : ''} today •{' '}
            {totalMarked}/{data.total} marked
          </p>

          <div className="space-y-3">
            {groupedClasses.map((cls) => {
              const key          = slotKey(cls.subject_id, cls.start_time);
              const isProcessing = markingId === key;
              const isMarked     = isClassMarked(cls);
              const markedAt     = getMarkedAt(cls);
              const markedTime   = fmtTime(markedAt);

              return (
                <div
                  key={key}
                  className="flex flex-col p-3 bg-slate-900/40 backdrop-blur-sm rounded-lg border border-slate-800/50 hover:border-slate-700/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    {isProcessing ? (
                      <Loader2 size={18} className="text-emerald-400 animate-spin" />
                    ) : isMarked ? (
                      <CheckCircle size={18} className="text-emerald-400" />
                    ) : (
                      <Circle size={18} className="text-slate-500" />
                    )}

                    <div className="flex-1">
                      <p className="text-white font-medium text-sm">{cls.subject_name}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {cls.start_time} - {cls.end_time}
                        {cls.room ? ` • ${cls.room}` : ''}
                      </p>
                      {/* Bug 2 — show marked timestamp after marking */}
                      {isMarked && markedTime && (
                        <p className="text-xs text-emerald-500/80 mt-0.5">
                          ✓ Marked at {markedTime}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Inline buttons for unmarked classes */}
                  {!isMarked && !isProcessing && (
                    <div className="flex flex-wrap gap-2 mt-3 pl-[30px]">
                      <button
                        onClick={() => handleMark(cls, 'present')}
                        className="px-3 py-2 min-h-[44px] text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors border border-emerald-500/20 flex-1 sm:flex-none"
                      >
                        Present
                      </button>
                      <button
                        onClick={() => handleMark(cls, 'absent')}
                        className="px-3 py-2 min-h-[44px] text-xs font-medium rounded-md bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 hover:text-rose-300 transition-colors border border-rose-500/20 flex-1 sm:flex-none"
                      >
                        Absent
                      </button>
                      <button
                        onClick={() => handleMark(cls, 'late')}
                        className="px-3 py-2 min-h-[44px] text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors border border-emerald-500/20 flex-1 sm:flex-none"
                      >
                        Late
                      </button>
                      <button
                        onClick={() => handleMark(cls, 'excused')}
                        className="px-3 py-2 min-h-[44px] text-xs font-medium rounded-md bg-slate-500/10 text-slate-300 hover:bg-slate-500/20 hover:text-white transition-colors border border-slate-500/20 flex-1 sm:flex-none"
                      >
                        Excused
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
