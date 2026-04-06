import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isSameDay, addMonths, subMonths, startOfWeek, endOfWeek } from 'date-fns';
import AssignmentDayCell from './AssignmentDayCell';
import AssignmentModal from './AssignmentModal';

export default function CalendarView({ assignments, onAssignmentClick, onStatusChange, onDocumentClick, onClassroomClick }) {
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [selectedAssignment, setSelectedAssignment] = useState(null);

    // Generate calendar days
    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(currentMonth);
    const calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 }); // Monday
    const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });

    const calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd });

    // Group assignments by date
    const assignmentsByDate = assignments.reduce((acc, assignment) => {
        if (!assignment.deadline) return acc;
        const dateKey = format(new Date(assignment.deadline), 'yyyy-MM-dd');
        if (!acc[dateKey]) acc[dateKey] = [];
        acc[dateKey].push(assignment);
        return acc;
    }, {});

    function previousMonth() {
        setCurrentMonth(subMonths(currentMonth, 1));
    }

    function nextMonth() {
        setCurrentMonth(addMonths(currentMonth, 1));
    }

    function handleAssignmentSelect(assignment) {
        if (assignment.sourceType === 'document') {
            onDocumentClick?.(assignment.sourceDocumentId);
            return;
        }
        if (assignment.sourceType === 'classroom') {
            onClassroomClick?.(assignment);
            return;
        }
        setSelectedAssignment(assignment);
    }

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-6 shadow-xl">
            {/* Header with Month Navigation */}
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-white">
                    {format(currentMonth, 'MMMM yyyy')}
                </h2>
                <div className="flex gap-2">
                    <button
                        onClick={previousMonth}
                        className="p-2 hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-white"
                    >
                        <ChevronLeft size={20} />
                    </button>
                    <button
                        onClick={() => setCurrentMonth(new Date())}
                        className="px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-400/10 rounded-lg transition-colors border border-emerald-400/20"
                    >
                        Today
                    </button>
                    <button
                        onClick={nextMonth}
                        className="p-2 hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-white"
                    >
                        <ChevronRight size={20} />
                    </button>
                </div>
            </div>

            {/* Calendar Grid */}
            <div className="grid grid-cols-7 gap-1 sm:gap-2">
                {/* Day Headers */}
                {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day, i) => (
                    <div key={day} className="text-center text-[10px] sm:text-xs font-bold text-slate-500 uppercase tracking-widest py-2">
                        <span className="hidden sm:inline">{day}</span>
                        <span className="sm:hidden">{day[0]}</span>
                    </div>
                ))}

                {/* Date Cells */}
                {calendarDays.map(day => {
                    const dateKey = format(day, 'yyyy-MM-dd');
                    const dayAssignments = assignmentsByDate[dateKey] || [];
                    const isCurrentMonth = isSameMonth(day, monthStart);
                    const isToday = isSameDay(day, new Date());

                    return (
                        <AssignmentDayCell
                            key={dateKey}
                            day={day}
                            assignments={dayAssignments}
                            isCurrentMonth={isCurrentMonth}
                            isToday={isToday}
                            onClick={handleAssignmentSelect}
                        />
                    );
                })}
            </div>

            {/* Legend */}
            <div className="mt-8 pt-6 border-t border-slate-800 flex flex-wrap gap-x-6 gap-y-3 text-[10px] sm:text-xs font-medium uppercase tracking-wider">
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.3)]" />
                    <span className="text-slate-500">High Priority</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.3)]" />
                    <span className="text-slate-500">Medium</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]" />
                    <span className="text-slate-500">Low</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.3)]" />
                    <span className="text-slate-500">Completed</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(192,132,252,0.3)]" />
                    <span className="text-slate-500">Document Deadline</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-slate-500">⏱</span>
                    <span className="text-slate-500">Hover for time estimate</span>
                </div>
            </div>

            {/* Assignment Detail Modal */}
            {selectedAssignment && (
                <AssignmentModal
                    assignment={selectedAssignment}
                    onClose={() => setSelectedAssignment(null)}
                    onStatusChange={onStatusChange}
                />
            )}
        </div>
    );
}
