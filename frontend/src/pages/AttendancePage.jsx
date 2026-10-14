/**
 * src/pages/AttendancePage.jsx
 * ──────────────────────────────
 * Attendance dashboard supporting:
 * 1. Official Class Attendance for enrolled students (Phase 6B).
 * 2. Independent / Personal Attendance Tracker for independent students.
 */
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format } from "date-fns";
import { markAttendance, getSummary, getAttendanceAlerts, updateSubject, deleteSubject } from "../api/attendance";
import { classAttendanceAPI } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { PageHeader, Button, EmptyState, Spinner } from "../components/ui/components";
import {
  CalendarCheck, Plus, Building, Layers, CheckCircle2,
  XCircle, AlertCircle, Clock, ShieldCheck
} from "lucide-react";
import toast from "react-hot-toast";

// Components
import { SubjectCard } from "../components/attendance/SubjectCard";
import { AddSubjectModal } from "../components/attendance/AddSubjectModal";
import { EditSubjectModal } from "../components/attendance/EditSubjectModal";
import { CalendarModal } from "../components/attendance/CalendarModal";
import AlertBanner from "../components/attendance/AlertBanner";
import RecoveryPlanModal from "../components/attendance/RecoveryPlanModal";

export default function AttendancePage() {
  const { user } = useAuth();

  // Mode: "class" | "personal"
  const [attendanceMode, setAttendanceMode] = useState("personal");
  const [classAttendance, setClassAttendance] = useState(null);

  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingSubject, setEditingSubject] = useState(null);
  const [subjectSaving, setSubjectSaving] = useState(false);
  const [selectedHistory, setSelectedHistory] = useState(null); // { id, name }
  const [alerts, setAlerts] = useState([]);
  const [showRecoveryPlan, setShowRecoveryPlan] = useState(null);

  const todayDate = format(new Date(), "yyyy-MM-dd");

  async function loadAlerts() {
    try {
      const { data } = await getAttendanceAlerts();
      setAlerts(data);
    } catch {
      // Silently ignore alert load errors
    }
  }

  async function loadData() {
    try {
      const [personalRes, classRes] = await Promise.all([
        getSummary(),
        classAttendanceAPI.getStudentClassAttendance().catch(() => ({ data: { enrolled: false } })),
      ]);
      setSummaries(personalRes.data);

      if (classRes.data?.enrolled) {
        setClassAttendance(classRes.data);
        setAttendanceMode("class");
      } else {
        setClassAttendance(null);
        setAttendanceMode("personal");
      }
    } catch (err) {
      toast.error("Failed to load attendance data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    loadAlerts();
  }, []);

  async function handleMark(subjectId, status) {
    setActionLoading(true);
    try {
      await markAttendance({
        subject_id: subjectId,
        class_date: todayDate,
        status,
      });
      toast.success(`Marked as ${status}`);
      await loadData();
      await loadAlerts();
    } catch (err) {
      toast.error("Failed to mark attendance");
    } finally {
      setActionLoading(false);
    }
  }

  function handleViewHistory(id, name) {
    setSelectedHistory({ id, name });
  }

  async function handleSaveSubjectChanges(payload) {
    if (!editingSubject) return;

    setSubjectSaving(true);
    try {
      await updateSubject(editingSubject.subject_id, payload);
      toast.success("Subject updated");
      setEditingSubject(null);
      await loadData();
      await loadAlerts();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to update subject");
    } finally {
      setSubjectSaving(false);
    }
  }

  async function handleDeleteSubject(summary) {
    const confirmed = window.confirm(
      `Delete ${summary.subject_name}? This will also remove its attendance records.`
    );
    if (!confirmed) return;

    setActionLoading(true);
    try {
      await deleteSubject(summary.subject_id);
      toast.success("Subject deleted");
      await loadData();
      await loadAlerts();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to delete subject");
    } finally {
      setActionLoading(false);
    }
  }

  const prominentAlerts = alerts
    .filter((a) => a.severity === "critical" || a.severity === "warning")
    .slice(0, 3);

  if (loading) {
    return (
      <div className="p-4 md:p-8 max-w-7xl mx-auto">
        <div className="skeleton h-8 w-48 mb-2" />
        <div className="skeleton h-4 w-32 mb-8" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3">
              <div className="skeleton h-5 w-1/2" />
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-8 w-full rounded-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <CalendarCheck className="text-emerald-400" size={26} />
            Attendance Dashboard
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Today is {format(new Date(), "MMMM do, yyyy")}
          </p>
        </div>

        {/* View Switcher (Only shown if student is enrolled in a class cohort) */}
        {classAttendance?.enrolled && (
          <div className="flex items-center gap-1.5 p-1 bg-slate-900/80 border border-white/10 rounded-xl">
            <button
              onClick={() => setAttendanceMode("class")}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                attendanceMode === "class"
                  ? "bg-emerald-500 text-black shadow-md shadow-emerald-500/20"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Building size={14} /> Official Class Attendance
            </button>
            <button
              onClick={() => setAttendanceMode("personal")}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                attendanceMode === "personal"
                  ? "bg-emerald-500 text-black shadow-md shadow-emerald-500/20"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              <Layers size={14} /> Personal Tracker
            </button>
          </div>
        )}

        {/* Action Button for Personal Tracker */}
        {(!classAttendance?.enrolled || attendanceMode === "personal") && (
          <Button onClick={() => setShowAddModal(true)} className="gap-2 self-start md:self-auto">
            <Plus size={18} /> Add Subject
          </Button>
        )}
      </div>

      {/* Smart Alerts Section */}
      {prominentAlerts.length > 0 && (
        <div className="mb-6 space-y-2.5">
          {prominentAlerts.map((alert) => (
            <AlertBanner
              key={alert.id}
              alert={alert}
              onViewRecovery={(subjectId) => setShowRecoveryPlan(subjectId)}
            />
          ))}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          VIEW 1: OFFICIAL CLASS ATTENDANCE (PHASE 6B)
      ───────────────────────────────────────────────────────────── */}
      {classAttendance?.enrolled && attendanceMode === "class" && (
        <div className="space-y-6">
          {/* Class Banner */}
          <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-500/10 via-slate-900/80 to-slate-900 border border-emerald-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <ShieldCheck size={22} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-white">
                    {classAttendance.cohort.name}
                  </h2>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 font-mono">
                    {classAttendance.cohort.academic_year}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Official class records managed by your institution administration.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-[11px] text-slate-400 font-medium">Overall Attendance</p>
                <p className={`text-2xl font-bold font-mono ${
                  classAttendance.overall_percentage >= 75 ? "text-emerald-400" : "text-rose-400"
                }`}>
                  {classAttendance.overall_percentage}%
                </p>
              </div>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10">
              <p className="text-[11px] text-slate-400 font-medium uppercase tracking-wider">Total Classes</p>
              <p className="text-xl font-bold text-white mt-1 font-mono">{classAttendance.total_classes}</p>
            </div>
            <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
              <p className="text-[11px] text-emerald-400 font-medium uppercase tracking-wider">Attended</p>
              <p className="text-xl font-bold text-emerald-400 mt-1 font-mono">{classAttendance.present_count}</p>
            </div>
            <div className="p-4 rounded-xl bg-rose-500/5 border border-rose-500/20">
              <p className="text-[11px] text-rose-400 font-medium uppercase tracking-wider">Missed</p>
              <p className="text-xl font-bold text-rose-400 mt-1 font-mono">{classAttendance.absent_count}</p>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10">
              <p className="text-[11px] text-slate-400 font-medium uppercase tracking-wider">Status</p>
              <p className="text-sm font-bold mt-1">
                {classAttendance.total_classes < 3 ? (
                  <span className="text-slate-400">Initial Sessions</span>
                ) : classAttendance.overall_percentage >= 75 ? (
                  <span className="text-emerald-400 flex items-center gap-1"><CheckCircle2 size={14} /> Safe (&ge;75%)</span>
                ) : (
                  <span className="text-rose-400 flex items-center gap-1"><AlertCircle size={14} /> Low Attendance</span>
                )}
              </p>
            </div>
          </div>

          {/* Subjects Grid */}
          <div>
            <h3 className="text-sm font-bold text-white mb-3">Attendance by Subject</h3>
            {classAttendance.subjects.length === 0 ? (
              <div className="p-10 rounded-2xl bg-slate-900/50 border border-white/5 text-center">
                <Clock size={30} className="mx-auto text-slate-500 mb-2" />
                <p className="text-slate-300 font-medium text-sm">No Class Sessions Recorded</p>
                <p className="text-slate-500 text-xs mt-1">Your teacher has not recorded class sessions for this term yet.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {classAttendance.subjects.map((sub, idx) => (
                  <div
                    key={idx}
                    className="p-5 rounded-2xl bg-slate-900/60 border border-white/10 hover:border-white/20 transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <h4 className="font-bold text-white text-base truncate">{sub.subject_name}</h4>
                        {sub.total_classes >= 3 && sub.below_threshold ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                            Below 75%
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            Safe
                          </span>
                        )}
                      </div>

                      <div className="flex items-baseline justify-between mb-3">
                        <span className="text-2xl font-bold font-mono text-white">
                          {sub.attendance_percentage}%
                        </span>
                        <span className="text-xs text-slate-400 font-mono">
                          {sub.present_count} / {sub.total_classes} attended
                        </span>
                      </div>

                      {/* Progress bar */}
                      <div className="w-full h-2 rounded-full bg-black/40 overflow-hidden mb-3">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            sub.attendance_percentage >= 75 ? "bg-emerald-500" : "bg-rose-500"
                          }`}
                          style={{ width: `${Math.min(100, Math.max(0, sub.attendance_percentage))}%` }}
                        />
                      </div>
                    </div>

                    {sub.below_threshold && sub.classes_needed_to_recover > 0 && (
                      <p className="text-[11px] text-rose-300 font-medium bg-rose-500/10 p-2.5 rounded-xl border border-rose-500/20">
                        Attend <strong>{sub.classes_needed_to_recover} consecutive classes</strong> to recover above 75%.
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Class Records */}
          {classAttendance.recent_records.length > 0 && (
            <div>
              <h3 className="text-sm font-bold text-white mb-3">Recent Class Sessions</h3>
              <div className="rounded-2xl border border-white/10 bg-slate-900/50 overflow-hidden">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-white/10 bg-black/40 text-[11px] text-slate-400 uppercase tracking-wider font-semibold">
                      <th className="px-5 py-3">Date</th>
                      <th className="px-5 py-3">Subject</th>
                      <th className="px-5 py-3 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {classAttendance.recent_records.map((r) => (
                      <tr key={r.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="px-5 py-3 font-mono text-xs text-slate-300">
                          {r.class_date}
                        </td>
                        <td className="px-5 py-3 text-xs font-semibold text-white">
                          {r.subject_name}
                        </td>
                        <td className="px-5 py-3 text-right">
                          {r.status === "present" ? (
                            <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              Present
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                              Absent
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          VIEW 2: PERSONAL ATTENDANCE TRACKER (INDEPENDENT OR CUSTOM)
      ───────────────────────────────────────────────────────────── */}
      {(!classAttendance?.enrolled || attendanceMode === "personal") && (
        <div>
          {summaries.length === 0 ? (
            <EmptyState
              icon={CalendarCheck}
              message="No subjects added yet. Start tracking by adding your first subject."
              action={
                <Button onClick={() => setShowAddModal(true)} variant="outline">
                  Add Subject
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {summaries.map((summary, i) => (
                <motion.div
                  key={summary.subject_id}
                  initial={{ opacity: 0, y: 14, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.4, delay: i * 0.06, ease: [0.4, 0, 0.2, 1] }}
                >
                  <SubjectCard
                    summary={summary}
                    onMark={handleMark}
                    onViewHistory={handleViewHistory}
                    onViewRecovery={(subjectId) => setShowRecoveryPlan(subjectId)}
                    onEditSubject={setEditingSubject}
                    onDeleteSubject={handleDeleteSubject}
                    loading={actionLoading}
                  />
                </motion.div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Modals for Personal Tracker */}
      <AddSubjectModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSuccess={loadData}
      />

      <EditSubjectModal
        open={!!editingSubject}
        onClose={() => setEditingSubject(null)}
        subject={editingSubject}
        onSave={handleSaveSubjectChanges}
        loading={subjectSaving}
      />

      <CalendarModal
        open={!!selectedHistory}
        onClose={() => setSelectedHistory(null)}
        subjectId={selectedHistory?.id}
        subjectName={selectedHistory?.name}
      />

      <RecoveryPlanModal
        subjectId={showRecoveryPlan}
        onClose={() => setShowRecoveryPlan(null)}
      />
    </div>
  );
}
