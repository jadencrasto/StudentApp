import { useMemo, useState } from 'react';
import { CheckCircle, Circle, Sun, Loader2, Check } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { api } from '../../lib/api';

export default function MorningCheckin({ data }) {
  const [markingId, setMarkingId] = useState(null);
  const [localMarked, setLocalMarked] = useState([]);

  // Group continuous classes (double lectures)
  const groupedClasses = useMemo(() => {
    if (!data?.classes) return [];
    const grouped = [];
    let currentGroup = null;

    data.classes.forEach(cls => {
      // If continuous lecture of the same subject
      if (
        currentGroup &&
        currentGroup.subject_id === cls.subject_id &&
        currentGroup.end_time === cls.start_time
      ) {
        currentGroup.end_time = cls.end_time;
      } else {
        if (currentGroup) grouped.push(currentGroup);
        currentGroup = { ...cls };
      }
    });
    if (currentGroup) grouped.push(currentGroup);
    return grouped;
  }, [data?.classes]);

  const handleMark = async (subjectId, status) => {
    setMarkingId(subjectId);
    try {
      const todayDate = new Date().toISOString().split('T')[0];
      await api.post('/attendance/mark', {
        subject_id: subjectId,
        date: todayDate,
        status: status
      });
      setLocalMarked(prev => [...prev, subjectId]);
      toast.success('Attendance marked!');
    } catch (err) {
      toast.error('Failed to mark attendance.');
    } finally {
      setMarkingId(null);
    }
  };

  const handleMarkAllPresent = async () => {
    const unmarkedGroups = groupedClasses.filter(g => !g.is_marked && !localMarked.includes(g.subject_id));
    if (!unmarkedGroups.length) return;
    
    let promises = unmarkedGroups.map(g => 
      api.post('/attendance/mark', {
        subject_id: g.subject_id,
        date: new Date().toISOString().split('T')[0],
        status: 'present'
      }).then(() => g.subject_id)
    );

    toast.promise(Promise.all(promises), {
      loading: 'Marking all remaining as present...',
      success: 'All setup! Attendance marked.',
      error: 'Failed to mark all attendance.'
    }).then((ids) => {
      setLocalMarked(prev => [...prev, ...ids]);
    });
  };

  if (!data || !data.classes?.length) return null;

  const allMarked = groupedClasses.every(g => g.is_marked || localMarked.includes(g.subject_id));
  const totalMarked = data.marked + localMarked.length;

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
                className="text-xs font-semibold px-3 py-1.5 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 hover:text-emerald-200 transition-colors rounded-full flex items-center gap-1.5 border border-emerald-500/20"
              >
                <Check size={14} />
                Mark all Present
              </button>
            )}
          </div>
          
          <p className="text-emerald-100/80 text-sm mb-4">
            You have {data.total} class{data.total !== 1 ? 'es' : ''} today • {totalMarked}/{data.total} marked
          </p>

          <div className="space-y-3">
            {groupedClasses.map((cls) => {
              const isProcessing = markingId === cls.subject_id;
              const isMarked = cls.is_marked || localMarked.includes(cls.subject_id);

              return (
                <div key={`${cls.subject_id}-${cls.start_time}`} className="flex flex-col p-3 bg-slate-900/40 backdrop-blur-sm rounded-lg border border-slate-800/50 hover:border-slate-700/50 transition-colors">
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
                      <p className="text-xs text-slate-400 mt-0.5">{cls.start_time} - {cls.end_time}{cls.room ? ` • ${cls.room}` : ''}</p>
                    </div>
                  </div>

                  {/* Inline Buttons for unmarked classes */}
                  {!isMarked && !isProcessing && (
                    <div className="flex flex-wrap gap-2 mt-3 pl-[30px]">
                      <button 
                        onClick={() => handleMark(cls.subject_id, 'present')}
                        className="px-3 py-1.5 text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors border border-emerald-500/20"
                      >
                        Present
                      </button>
                      <button 
                        onClick={() => handleMark(cls.subject_id, 'absent')}
                        className="px-3 py-1.5 text-xs font-medium rounded-md bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 hover:text-rose-300 transition-colors border border-rose-500/20"
                      >
                        Absent
                      </button>
                      <button 
                        onClick={() => handleMark(cls.subject_id, 'late')}
                        className="px-3 py-1.5 text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors border border-emerald-500/20"
                      >
                        Late
                      </button>
                      <button 
                        onClick={() => handleMark(cls.subject_id, 'excused')}
                        className="px-3 py-1.5 text-xs font-medium rounded-md bg-slate-500/10 text-slate-300 hover:bg-slate-500/20 hover:text-white transition-colors border border-slate-500/20"
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
