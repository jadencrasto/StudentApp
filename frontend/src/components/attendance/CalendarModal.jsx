/**
 * src/components/attendance/CalendarModal.jsx
 * ──────────────────────────────────────────
 * Monthly calendar view of attendance history.
 */
import { useState, useEffect } from "react";
import { Modal, Spinner } from "../ui/components";
import { attendanceAPI } from "../../api/client";
import {
    format, startOfMonth, endOfMonth, startOfWeek, endOfWeek,
    eachDayOfInterval, isSameMonth, isSameDay, addMonths, subMonths
} from "date-fns";
import { ChevronLeft, ChevronRight, Check, X, Clock, ShieldAlert } from "lucide-react";
import { clsx } from "clsx";

const STATUS_ICONS = {
    present: { icon: Check, color: "bg-emerald-500", text: "text-emerald-500" },
    absent: { icon: X, color: "bg-rose-500", text: "text-rose-500" },
    late: { icon: Clock, color: "bg-amber-500", text: "text-amber-500" },
    excused: { icon: ShieldAlert, color: "bg-sky-500", text: "text-sky-500" },
};

export function CalendarModal({ open, onClose, subjectId, subjectName }) {
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open && subjectId) {
            loadHistory();
        }
    }, [open, subjectId]);

    async function loadHistory() {
        setLoading(true);
        try {
            const { data } = await attendanceAPI.getHistory(subjectId);
            setHistory(data);
        } catch (err) {
            console.error("Failed to load history", err);
        } finally {
            setLoading(false);
        }
    }

    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(monthStart);
    const startDate = startOfWeek(monthStart, { weekStartsOn: 1 });
    const endDate = endOfWeek(monthEnd, { weekStartsOn: 1 });

    const calendarDays = eachDayOfInterval({ start: startDate, end: endDate });

    return (
        <Modal open={open} onClose={onClose} title={`${subjectName} History`}>
            <div className="space-y-6">
                {/* Month Navigation */}
                <div className="flex items-center justify-between pb-2">
                    <button
                        onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
                        className="p-1 hover:bg-slate-800 rounded-lg text-slate-400"
                    >
                        <ChevronLeft size={20} />
                    </button>
                    <h3 className="font-semibold text-paper">
                        {format(currentMonth, "MMMM yyyy")}
                    </h3>
                    <button
                        onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
                        className="p-1 hover:bg-slate-800 rounded-lg text-slate-400"
                    >
                        <ChevronRight size={20} />
                    </button>
                </div>

                {loading ? (
                    <div className="flex justify-center py-12"><Spinner /></div>
                ) : (
                    <>
                        {/* Calendar Grid */}
                        <div className="grid grid-cols-7 gap-1">
                            {["M", "T", "W", "T", "F", "S", "S"].map((day, i) => (
                                <div key={i} className="text-center text-[10px] font-bold text-slate-500 py-1 uppercase tracking-widest">
                                    {day}
                                </div>
                            ))}

                            {calendarDays.map((dateObj, i) => {
                                const record = history.find(h => isSameDay(new Date(h.class_date), dateObj));
                                const statusInfo = record ? STATUS_ICONS[record.status] : null;
                                const isCurrentMonth = isSameMonth(dateObj, monthStart);

                                return (
                                    <div
                                        key={i}
                                        className={clsx(
                                            "aspect-square relative flex items-center justify-center rounded-lg text-sm transition-colors border",
                                            !isCurrentMonth ? "text-slate-700 border-transparent" : "text-slate-300 border-slate-800/50 hover:bg-slate-800/50",
                                            statusInfo && "border-opacity-0"
                                        )}
                                    >
                                        <span className={clsx(statusInfo && "opacity-20")}>
                                            {format(dateObj, "d")}
                                        </span>
                                        {statusInfo && (
                                            <div className={clsx("absolute inset-0 flex items-center justify-center rounded-lg bg-opacity-10", statusInfo.color.replace("bg-", "bg-"))}>
                                                <statusInfo.icon size={14} className={statusInfo.text} strokeWidth={3} />
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>

                        {/* Legend */}
                        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 pt-4 border-t border-slate-800/50 text-[10px] text-slate-500 font-medium uppercase tracking-wider">
                            <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-emerald-500" /> Present </div>
                            <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-rose-500" /> Absent </div>
                            <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-amber-500" /> Late </div>
                            <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-sky-500" /> Excused </div>
                        </div>
                    </>
                )}
            </div>
        </Modal>
    );
}
