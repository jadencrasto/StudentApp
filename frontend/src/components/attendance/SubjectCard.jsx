/**
 * src/components/attendance/SubjectCard.jsx
 * ──────────────────────────────────────────
 * Main card displaying summary and quick mark tools.
 */
import { Badge, Card } from "../ui/components";
import { ProgressBar } from "./ProgressBar";
import { QuickMarkButtons } from "./QuickMarkButtons";
import { Calendar, Info, Pencil, Trash2, TrendingUp } from "lucide-react";
import { clsx } from "clsx";

export function SubjectCard({ summary, onMark, onViewHistory, onViewRecovery, onEditSubject, onDeleteSubject, loading }) {
    const {
        subject_id,
        subject_name,
        subject_code,
        total_classes,
        present_count,
        attendance_percentage,
        below_threshold
    } = summary;

    // Determine color theme based on percentage
    const getTheme = (pct) => {
        if (pct >= 85) return { colorClass: "bg-emerald-500", textClass: "text-emerald-500", borderClass: "border-emerald-500/30" };
        if (pct >= 75) return { colorClass: "bg-emerald-500", textClass: "text-emerald-500", borderClass: "border-emerald-500/30" };
        return { colorClass: "bg-rose-500", textClass: "text-rose-500", borderClass: "border-rose-500/30" };
    };

    const theme = getTheme(attendance_percentage);

    // Calculate classes needed to reach 75%
    // Equation: (present + x) / (total + x) = 0.75 => x = 3*total - 4*present
    const classesNeeded = Math.max(0, 3 * total_classes - 4 * present_count);

    return (
        <Card className={clsx("relative overflow-hidden border-l-4", theme.borderClass)}>
            <div className="flex justify-between items-start mb-5">
                <div>
                    <h3 className="text-paper font-display font-bold text-lg leading-tight">{subject_name}</h3>
                    <span className="text-slate-500 text-xs font-mono uppercase tracking-widest">{subject_code || "No Code"}</span>
                </div>
                <div className="text-right">
                    <div className={clsx("text-3xl font-display font-black", theme.textClass)}>
                        {Math.round(attendance_percentage)}%
                    </div>
                    <div className="text-[10px] text-slate-500 font-bold uppercase tracking-tight">
                        {present_count} / {total_classes} Classes
                    </div>
                </div>
            </div>

            <div className="space-y-4">
                {/* Progress Display */}
                <ProgressBar percentage={attendance_percentage} colorClass={theme.colorClass} />

                {/* Insight/Warning Box */}
                {below_threshold ? (
                    <div className="flex gap-2.5 p-3 rounded-xl bg-rose-500/5 border border-rose-500/10">
                        <Info size={16} className="text-rose-500 shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                            <p className="text-xs text-rose-200 leading-relaxed">
                                Below threshold. You need <span className="font-bold text-rose-500">{classesNeeded}</span> more consecutive present marks to reach 75%.
                            </p>
                            {onViewRecovery && (
                                <button
                                    onClick={() => onViewRecovery(subject_id)}
                                    className="inline-flex items-center gap-1 mt-2 text-xs text-rose-400 hover:text-rose-300 font-semibold transition-colors"
                                >
                                    <TrendingUp size={11} />
                                    View Recovery Plan
                                </button>
                            )}
                        </div>
                    </div>
                ) : attendance_percentage >= 85 ? (
                    <div className="flex gap-2.5 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
                        <Info size={16} className="text-emerald-500 shrink-0 mt-0.5" />
                        <p className="text-xs text-emerald-200 leading-relaxed">
                            Safe zone! Maintaining this level gives you flexibility for future absences.
                        </p>
                    </div>
                ) : (
                    <div className="flex gap-2.5 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
                        <Info size={16} className="text-emerald-500 shrink-0 mt-0.5" />
                        <p className="text-xs text-emerald-200 leading-relaxed">
                            Watch out. You are close to the 75% limit. Avoid missing more classes.
                        </p>
                    </div>
                )}

                {/* Attendance Tools */}
                <div className="pt-2">
                    <QuickMarkButtons
                        onMark={(status) => onMark(subject_id, status)}
                        loading={loading}
                    />
                </div>

                {/* Bottom Actions */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <button
                        onClick={() => onViewHistory(subject_id, subject_name)}
                        className="sm:col-span-3 w-full flex items-center justify-center gap-2 py-2 text-xs font-bold text-slate-400 hover:text-paper hover:bg-slate-800 rounded-xl transition-all"
                    >
                        <Calendar size={14} /> View History &amp; Attendance Log
                    </button>

                    <button
                        onClick={() => onEditSubject?.(summary)}
                        className="w-full flex items-center justify-center gap-2 py-2 text-xs font-bold text-emerald-400 hover:text-emerald-300 hover:bg-emerald-400/10 rounded-xl transition-all"
                    >
                        <Pencil size={13} /> Edit
                    </button>

                    <button
                        onClick={() => onDeleteSubject?.(summary)}
                        className="w-full flex items-center justify-center gap-2 py-2 text-xs font-bold text-rose-400 hover:text-rose-300 hover:bg-rose-400/10 rounded-xl transition-all"
                    >
                        <Trash2 size={13} /> Delete
                    </button>
                </div>
            </div>
        </Card>
    );
}
