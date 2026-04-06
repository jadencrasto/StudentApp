import { format } from 'date-fns';

export default function AssignmentDayCell({ day, assignments, isCurrentMonth, isToday, onClick }) {
    const dayNumber = format(day, 'd');

    // Sort by priority (high -> medium -> low)
    const sortedAssignments = [...assignments].sort((a, b) => {
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        return priorityOrder[a.priority] - priorityOrder[b.priority];
    });

    const getPriorityColor = (priority) => {
        const colors = {
            high: 'bg-red-400',
            medium: 'bg-emerald-400',
            low: 'bg-emerald-500'
        };
        return colors[priority] || 'bg-slate-600';
    };

    const getStatusColor = (status) => {
        if (status === 'completed') return 'bg-emerald-400';
        if (status === 'overdue') return 'bg-rose-400';
        return '';
    };

    const getTypeColor = (assignment) => {
        if (assignment.sourceType === 'document') return 'bg-purple-400';
        if (assignment.sourceType === 'classroom') {
            if (assignment.classroomSubmissionStatus === 'submitted') return 'bg-emerald-400';
            if (assignment.classroomSubmissionStatus === 'late_submit') return 'bg-emerald-600';
            if (assignment.classroomSubmissionStatus === 'missing') return 'bg-rose-400';
            return 'bg-emerald-400';
        }
        return getStatusColor(assignment.status) || getPriorityColor(assignment.priority);
    };

    const getClassroomStatusLabel = (assignment) => {
        const status = assignment.classroomSubmissionStatus;
        if (status === 'submitted') return 'SUBMITTED';
        if (status === 'late_submit') return 'LATE';
        if (status === 'missing') return 'MISSING';
        return 'ASSIGNED';
    };

    return (
        <div
            className={`min-h-[80px] sm:min-h-[100px] p-1.5 sm:p-2.5 rounded-xl border transition-all duration-300 ${isCurrentMonth
                    ? 'bg-slate-800/40 border-slate-700/50 hover:bg-slate-800/80 hover:border-slate-600 shadow-sm'
                    : 'bg-slate-900/40 border-transparent opacity-20'
                } ${isToday ? 'ring-2 ring-emerald-400/40 bg-slate-800/80 border-emerald-400/20 shadow-[0_0_15px_rgba(52,211,153,0.1)]' : ''}`}
        >
            {/* Day Number */}
            <div className="flex items-center justify-between mb-2">
                <span
                    className={`text-[13px] font-bold ${isToday
                            ? 'text-emerald-400'
                            : isCurrentMonth
                                ? 'text-slate-400'
                                : 'text-slate-600'
                        }`}
                >
                    {dayNumber}
                </span>
                {assignments.length > 0 && isCurrentMonth && (
                    <span className="text-[10px] font-bold text-slate-500 bg-slate-800/80 px-1.5 py-0.5 rounded-md border border-slate-700/50">
                        {assignments.length}
                    </span>
                )}
            </div>

            {/* Assignment Indicators */}
            <div className="space-y-1">
                {isCurrentMonth && sortedAssignments.slice(0, 3).map((assignment) => {
                    const statusColor = assignment.sourceType === 'document' ? '' : getStatusColor(assignment.status);
                    const priorityColor = assignment.sourceType === 'document' ? 'bg-purple-400' : assignment.sourceType === 'classroom' ? 'bg-emerald-400' : getPriorityColor(assignment.priority);
                    const typeColor = getTypeColor(assignment);

                    return (
                        <button
                            key={assignment.id}
                            onClick={() => onClick(assignment)}
                            className={`w-full text-left px-2 py-1 rounded-lg text-[10px] font-bold truncate transition-all duration-200 border border-transparent hover:scale-[1.02] ${statusColor
                                    ? `${statusColor} text-white shadow-sm`
                                    : `${priorityColor}/10 ${priorityColor.replace('bg-', 'text-')} hover:bg-${priorityColor.replace('bg-', '')}/20 border-${priorityColor.replace('bg-', '')}/20`
                                }`}
                            title={`${assignment.title}${assignment.ai_metadata?.time_estimate ? ` · ⏱ ${assignment.ai_metadata.time_estimate.estimated_hours}h (${assignment.ai_metadata.time_estimate.complexity})` : ''}`}
                        >
                            <div className="flex items-center gap-1.5">
                                <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${typeColor} ${!statusColor && assignment.sourceType !== 'document' && 'animate-pulse'}`} />
                                <span className="truncate">{assignment.title}</span>
                                {assignment.ai_metadata?.time_estimate && !assignment.sourceType && (
                                    <span className="ml-auto flex-shrink-0 text-[8px] font-bold opacity-70">
                                        ⏱{assignment.ai_metadata.time_estimate.estimated_hours}h
                                    </span>
                                )}
                                {assignment.sourceType === 'document' && (
                                    <span className="ml-auto text-[8px] font-bold uppercase tracking-wider text-purple-200/90">DOC</span>
                                )}
                                {assignment.sourceType === 'classroom' && (
                                    <span className="ml-auto text-[8px] font-bold uppercase tracking-wider text-cyan-200/90">{getClassroomStatusLabel(assignment)}</span>
                                )}
                            </div>
                        </button>
                    );
                })}

                {/* Show "+N more" if there are more than 3 */}
                {isCurrentMonth && assignments.length > 3 && (
                    <div className="text-[9px] font-bold text-slate-500 pl-1 uppercase tracking-wider">
                        +{assignments.length - 3} more
                    </div>
                )}
            </div>
        </div>
    );
}
