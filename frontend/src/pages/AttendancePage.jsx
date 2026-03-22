/**
 * src/pages/AttendancePage.jsx
 * ──────────────────────────────
 * Redesigned Attendance dashboard using new hybrid components.
 */
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format } from "date-fns";
import { markAttendance, getSummary, getAttendanceAlerts, updateSubject, deleteSubject } from "../api/attendance";
import { PageHeader, Button, EmptyState, Spinner } from "../components/ui/components";
import { CalendarCheck, Plus } from "lucide-react";
import toast from "react-hot-toast";

// New Components
import { SubjectCard } from "../components/attendance/SubjectCard";
import { AddSubjectModal } from "../components/attendance/AddSubjectModal";
import { EditSubjectModal } from "../components/attendance/EditSubjectModal";
import { CalendarModal } from "../components/attendance/CalendarModal";
import AlertBanner from "../components/attendance/AlertBanner";
import RecoveryPlanModal from "../components/attendance/RecoveryPlanModal";

export default function AttendancePage() {
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
      const { data } = await getSummary();
      setSummaries(data);
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
      await loadData(); // Refresh percentages
      await loadAlerts(); // Refresh alerts too
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

  // Show only critical + warning alerts at the top (max 3)
  const prominentAlerts = alerts
    .filter((a) => a.severity === "critical" || a.severity === "warning")
    .slice(0, 3);

  if (loading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
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
    <div className="p-8 max-w-7xl mx-auto">
      <PageHeader
        title="Attendance Tracker"
        subtitle={`Today is ${format(new Date(), "MMMM do, yyyy")}`}
        action={
          <Button onClick={() => setShowAddModal(true)} className="gap-2">
            <Plus size={18} /> Add Subject
          </Button>
        }
      />

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

      {/* Modals */}
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
