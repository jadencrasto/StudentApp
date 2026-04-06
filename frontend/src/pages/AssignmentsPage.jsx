import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { getAssignments, createAssignment, updateAssignment, deleteAssignment, estimateAllAssignments, estimateAssignment } from '../api/assignments'
import { getDocuments, reprocessDocument } from '../api/documents'
import client from '../api/client'
import { format } from 'date-fns'
import { Plus, Trash2, CheckCircle, Clock, AlertCircle, BookOpen, X, Calendar as CalendarIcon, List, RefreshCw, FileText, ChevronDown, ChevronUp } from 'lucide-react'
import CalendarView from '../components/assignments/CalendarView'
import toast from 'react-hot-toast'

const TASK_TYPES = ['assignment', 'exam', 'quiz', 'project', 'announcement', 'other']
const PRIORITIES = ['low', 'medium', 'high']
const STATUSES = ['pending', 'in_progress', 'completed', 'overdue']

const typeColors = { assignment: 'bg-emerald-400/10 text-emerald-400', exam: 'bg-red-400/10 text-red-400', quiz: 'bg-purple-400/10 text-purple-400', project: 'bg-green-400/10 text-green-400', announcement: 'bg-emerald-400/10 text-emerald-400', other: 'bg-slate-600/30 text-slate-400' }
const statusIcons = { pending: <Clock size={14} />, in_progress: <AlertCircle size={14} />, completed: <CheckCircle size={14} />, overdue: <AlertCircle size={14} /> }
const statusColors = { pending: 'text-emerald-400', in_progress: 'text-emerald-400', completed: 'text-emerald-400', overdue: 'text-red-400' }
const classroomStatusColors = { submitted: 'text-emerald-400', graded: 'text-emerald-400', missing: 'text-red-400', assigned: 'text-emerald-400', 'no due date': 'text-slate-400' }

function AssignmentModal({ onClose, onSave }) {
  const [form, setForm] = useState({ title: '', subject: '', task_type: 'assignment', description: '', deadline: '', priority: 'medium' })
  const [saving, setSaving] = useState(false)
  async function submit(e) {
    e.preventDefault(); setSaving(true)
    try {
      const cleanForm = Object.fromEntries(
        Object.entries(form).map(([key, val]) => [key, val === '' ? null : val])
      )
      await onSave(cleanForm)
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create')
    } finally { setSaving(false) }
  }
  const inp = "w-full px-3 py-2 bg-black/40 border border-white/10 rounded-lg text-sm text-gray-100 focus:outline-none focus:border-emerald-500 transition-all"
  const lbl = "block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wider"
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.93, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 8 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        onClick={e => e.stopPropagation()}
        className="bg-black/80 border border-white/10 rounded-2xl w-full max-w-md backdrop-blur-md"
      >
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="font-display text-xl text-white">New Assignment</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300"><X size={20} /></button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          <div><label className={lbl}>Title *</label><input className={inp} required value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="Assignment title" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={lbl}>Subject</label><input className={inp} value={form.subject} onChange={e => setForm(f => ({ ...f, subject: e.target.value }))} placeholder="e.g. Physics" /></div>
            <div><label className={lbl}>Deadline</label><input className={inp} type="date" value={form.deadline} onChange={e => setForm(f => ({ ...f, deadline: e.target.value }))} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={lbl}>Type</label>
              <select className={inp} value={form.task_type} onChange={e => setForm(f => ({ ...f, task_type: e.target.value }))}>
                {TASK_TYPES.map(t => <option key={t}>{t}</option>)}</select></div>
            <div><label className={lbl}>Priority</label>
              <select className={inp} value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
                {PRIORITIES.map(p => <option key={p}>{p}</option>)}</select></div>
          </div>
          <div><label className={lbl}>Description</label><textarea className={`${inp} resize-none`} rows={3} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Optional notes..." /></div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2.5 border border-white/10 rounded-xl text-sm text-gray-400 hover:text-gray-200 transition-all">Cancel</button>
            <button type="submit" disabled={saving} className="flex-1 py-2.5 bg-emerald-500 text-black font-semibold rounded-xl text-sm hover:bg-emerald-600 transition-all disabled:opacity-50">
              {saving ? 'Saving...' : 'Create'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}

export default function AssignmentsPage() {
  const navigate = useNavigate()
  const [assignments, setAssignments] = useState([])
  const [documents, setDocuments] = useState([])
  const [classroomEvents, setClassroomEvents] = useState([])
  const [filter, setFilter] = useState({ status: '', subject: '' })
  const [showModal, setShowModal] = useState(false)
  const [view, setView] = useState('list') // 'list' or 'calendar'
  const [showDocs, setShowDocs] = useState(false)
  const [reprocessingId, setReprocessingId] = useState(null)
  const [estimatingId, setEstimatingId] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      // 1. Load local assignments + documents immediately (fast)
      const [assignmentsResult, documentsResult] = await Promise.allSettled([
        getAssignments(filter),
        getDocuments(),
      ])

      if (assignmentsResult.status === 'fulfilled') {
        setAssignments(assignmentsResult.value.data || [])
      }
      if (documentsResult.status === 'fulfilled') {
        setDocuments(documentsResult.value.data || [])
      }
    } finally {
      setLoading(false)
    }

    // 2. Trigger classroom sync in background (fire-and-forget, non-blocking).
    client.get('/classroom/events')
      .then(async (resp) => {
        setClassroomEvents(resp.data || [])
        try {
          const refreshed = await getAssignments(filter)
          setAssignments(refreshed.data || [])
        } catch { /* non-blocking */ }
      })
      .catch(() => setClassroomEvents([]))
  }

  useEffect(() => { load() }, [filter])

  async function handleCreate(form) {
    await createAssignment(form); load(); toast.success('Assignment created!')
  }

  async function handleReestimate(id) {
    setEstimatingId(id)
    try {
      await estimateAssignment(id)
      load()
      toast.success('Time estimate updated')
    } catch { toast.error('Estimation failed') }
    finally { setEstimatingId(null) }
  }

  async function handleReprocess(docId) {
    setReprocessingId(docId)
    try {
      await reprocessDocument(docId)
      toast.success('Re-scraping started — refresh in a moment')
      setTimeout(() => { load(); setReprocessingId(null) }, 4000)
    } catch { toast.error('Re-process failed'); setReprocessingId(null) }
  }

  async function handleStatusChange(id, status) {
    await updateAssignment(id, { status }).catch(() => toast.error('Update failed'))
    load()
  }

  async function handleDelete(id) {
    if (!confirm('Delete this assignment?')) return
    await deleteAssignment(id).catch(() => toast.error('Delete failed'))
    load(); toast.success('Deleted')
  }

  const documentCalendarItems = documents
    .map((doc) => {
      const extracted = doc.extracted_data || {}
      const deadline = extracted.deadline
      if (!deadline) return null

      return {
        id: `doc-${doc.id}`,
        sourceDocumentId: doc.id,
        title: extracted.title || doc.original_filename || doc.filename || 'Document deadline',
        subject: extracted.subject || 'Document',
        task_type: extracted.task_type || 'document',
        deadline,
        priority: 'medium',
        status: 'pending',
        sourceType: 'document',
      }
    })
    .filter(Boolean)

  const classroomCalendarItems = classroomEvents
    .filter((event) => event?.type === 'Assignment')
    .map((event, idx) => ({
      id: `classroom-${idx}-${event.title || 'assignment'}`,
      title: event.title || 'Classroom Assignment',
      subject: event.course || 'Google Classroom',
      task_type: 'assignment',
      deadline: event.due_date,
      priority: 'medium',
      status: event.submission_status === 'submitted' ? 'completed' : 'pending',
      classroomSubmissionStatus: event.submission_status || 'assigned',
      classroomSubmissionState: event.submission_state || null,
      link: event.link || null,
      sourceType: 'classroom',
    }))

  // Classroom assignments are now synced to the DB, so they appear in 'assignments'.
  // Use classroom_id to detect classroom-sourced assignments for special rendering.
  const listItems = assignments.map(a => ({
    ...a,
    sourceType: a.classroom_id ? 'classroom' : undefined,
    classroomLabel: a.ai_metadata?.classroom?.classroom_label || a.ai_metadata?.classroom?.submission_status || undefined,
    classroomSubmissionStatus: a.ai_metadata?.classroom?.submission_status || undefined,
    classroomSubmissionState: a.ai_metadata?.classroom?.workflow_status || undefined,
    link: a.ai_metadata?.classroom?.link || undefined,
  }))
  const calendarItems = [
    ...assignments.map(a => ({
      ...a,
      sourceType: a.classroom_id ? 'classroom' : undefined,
      link: a.ai_metadata?.classroom?.link || undefined,
    })),
    ...documentCalendarItems,
  ].filter((item) => item.deadline)

  return (
    <div className="p-8">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-center justify-between mb-8"
      >
        <div>
          <h1 className="font-display text-3xl text-white">Assignments</h1>
          <p className="text-slate-400 text-sm mt-1">{listItems.length} total</p>
        </div>

        <div className="flex items-center gap-3">
          {/* View Toggle */}
          <div className="flex items-center gap-1 bg-black/40 rounded-xl p-1 border border-white/10">
            <button
              onClick={() => setView('list')}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold transition-all duration-300 ${view === 'list'
                ? 'bg-slate-700 text-white shadow-lg'
                : 'text-slate-500 hover:text-slate-300'
                }`}
            >
              <List size={14} />
              LIST
            </button>
            <button
              onClick={() => setView('calendar')}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold transition-all duration-300 ${view === 'calendar'
                ? 'bg-slate-700 text-white shadow-lg'
                : 'text-slate-500 hover:text-slate-300'
                }`}
            >
              <CalendarIcon size={14} />
              CALENDAR
            </button>
          </div>

          <motion.button
            whileHover={{ scale: 1.03, boxShadow: '0 0 24px rgba(16,185,129,0.25)' }}
            whileTap={{ scale: 0.97 }}
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500 text-black font-bold rounded-xl hover:bg-emerald-600 transition-colors text-sm shadow-[0_0_20px_rgba(16,185,129,0.2)]"
          >
            <Plus size={16} /> New Assignment
          </motion.button>
        </div>
      </motion.div>

      {/* Conditional Rendering */}
      {loading ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-4"
        >
          {[...Array(6)].map((_, i) => (
            <div key={i} className="skeleton h-14 w-full rounded-xl" style={{ animationDelay: `${i * 0.1}s` }} />
          ))}
        </motion.div>
      ) : view === 'list' ? (
        <>
          {/* Filters */}
          <div className="flex gap-3 mb-6">
            {['', 'pending', 'in_progress', 'completed', 'overdue'].map(s => (
              <button key={s} onClick={() => setFilter(f => ({ ...f, status: s }))}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${filter.status === s ? 'bg-emerald-500 text-black' : 'bg-white/5 text-gray-400 hover:text-gray-200 border border-white/10'}`}>
                {s || 'All'}
              </button>
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="bg-white/[0.02] border border-white/10 rounded-2xl overflow-hidden"
          >
            {listItems.length === 0
              ? <div className="py-16 text-center"><BookOpen size={32} className="text-slate-600 mx-auto mb-3" /><p className="text-slate-500">No assignments yet</p></div>
              : <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    {['Title', 'Subject', 'Type', 'Estimate', 'Deadline', 'Priority', 'Status', ''].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {listItems.map(a => (
                    <tr key={a.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-all">
                      <td className="px-4 py-3 text-sm text-slate-200 font-medium max-w-xs truncate">{a.title}</td>
                      <td className="px-4 py-3 text-sm text-slate-400">{a.subject || '—'}</td>
                      <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-md text-xs font-medium ${typeColors[a.task_type] || typeColors.other}`}>{a.task_type}</span></td>
                      <td className="px-4 py-3">
                        {a.ai_metadata?.time_estimate ? (
                          <div className="flex items-center gap-2">
                            <Clock size={14} className="text-emerald-400" />
                            <span className="text-sm text-slate-300">
                              {a.ai_metadata.time_estimate.estimated_hours}h
                            </span>
                            <span className="text-xs text-slate-500">
                              ({a.ai_metadata.time_estimate.complexity})
                            </span>
                          </div>
                        ) : !a.sourceType ? (
                          <button
                            onClick={() => handleReestimate(a.id)}
                            disabled={estimatingId === a.id}
                            className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 disabled:opacity-50 transition-all"
                          >
                            <RefreshCw size={12} className={estimatingId === a.id ? 'animate-spin' : ''} />
                            Estimate
                          </button>
                        ) : (
                          <span className="text-xs text-slate-500">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-slate-300">{a.deadline ? format(new Date(a.deadline), 'MMM d, yy') : '—'}</td>
                      <td className="px-4 py-3 text-sm text-slate-400 capitalize">{a.priority}</td>
                      <td className="px-4 py-3">
                        {a.sourceType === 'classroom' ? (
                          <span className={`text-xs font-medium ${classroomStatusColors[a.classroomLabel] || 'text-slate-300'}`}>
                            {(a.classroomLabel || 'assigned')}
                          </span>
                        ) : (
                          <select value={a.status} onChange={e => handleStatusChange(a.id, e.target.value)}
                            className={`text-xs font-medium bg-transparent border-0 outline-none cursor-pointer ${statusColors[a.status]}`}>
                            {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {a.sourceType === 'classroom' ? (
                          <span className="text-xs text-slate-600">—</span>
                        ) : (
                          <button onClick={() => handleDelete(a.id)} className="text-slate-600 hover:text-red-400 transition-all"><Trash2 size={14} /></button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          </motion.div>

          {/* ── Scraped Documents Panel ── */}
          {documents.length > 0 && (
            <div className="mt-6 bg-white/[0.02] border border-white/10 rounded-2xl overflow-hidden">
              <button
                onClick={() => setShowDocs(d => !d)}
                className="w-full flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-all"
              >
                <div className="flex items-center gap-3">
                  <FileText size={16} className="text-purple-400" />
                  <span className="text-sm font-semibold text-white">Scraped Documents</span>
                  <span className="text-xs bg-white/5 text-gray-400 px-2 py-0.5 rounded-md border border-white/10">{documents.length}</span>
                  {documents.filter(d => d.extraction_status === 'failed').length > 0 && (
                    <span className="text-xs bg-red-400/10 text-red-400 px-2 py-0.5 rounded-md">
                      {documents.filter(d => d.extraction_status === 'failed').length} failed
                    </span>
                  )}
                </div>
                {showDocs ? <ChevronUp size={16} className="text-slate-500" /> : <ChevronDown size={16} className="text-slate-500" />}
              </button>
              {showDocs && (
                <table className="w-full">
                  <thead>
                    <tr className="border-t border-b border-slate-800">
                      {['File', 'Status', 'Extracted Title', 'Subject', 'Deadline', 'Est. Time', ''].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map(doc => {
                      const ext = doc.extracted_data || {}
                      const te = ext.time_estimate
                      const statusColors2 = {
                        done: 'text-emerald-400 bg-emerald-400/10',
                        processing: 'text-blue-400 bg-blue-400/10',
                        pending: 'text-amber-400 bg-amber-400/10',
                        failed: 'text-red-400 bg-red-400/10',
                      }
                      return (
                        <tr key={doc.id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-all">
                          <td className="px-4 py-3 text-sm text-slate-300 max-w-[180px] truncate" title={doc.original_filename}>
                            {doc.original_filename || '—'}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${statusColors2[doc.extraction_status] || 'text-slate-400 bg-slate-700'}`}>
                              {doc.extraction_status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-slate-400 max-w-[180px] truncate">{ext.title || '—'}</td>
                          <td className="px-4 py-3 text-sm text-slate-400">{ext.subject || '—'}</td>
                          <td className="px-4 py-3 text-sm font-mono text-slate-300">
                            {ext.deadline ? format(new Date(ext.deadline), 'MMM d, yy') : '—'}
                          </td>
                          <td className="px-4 py-3">
                            {te ? (
                              <div className="flex items-center gap-1.5">
                                <Clock size={13} className="text-emerald-400" />
                                <span className="text-sm text-slate-300">{te.estimated_hours}h</span>
                                <span className="text-xs text-slate-500">({te.complexity})</span>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-600">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => handleReprocess(doc.id)}
                              disabled={reprocessingId === doc.id || doc.extraction_status === 'processing'}
                              title="Re-scrape document"
                              className="flex items-center gap-1 text-xs text-gray-500 hover:text-emerald-400 disabled:opacity-40 transition-all"
                            >
                              <RefreshCw size={13} className={reprocessingId === doc.id ? 'animate-spin text-amber-400' : ''} />
                              {reprocessingId === doc.id ? 'Scraping...' : 'Re-scrape'}
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      ) : (
        <CalendarView
          assignments={calendarItems}
          onStatusChange={handleStatusChange}
          onClassroomClick={(assignment) => {
            if (assignment?.link) {
              window.open(assignment.link, '_blank', 'noopener,noreferrer')
            }
          }}
          onDocumentClick={(documentId) => navigate(`/upload?doc=${documentId}`)}
        />
      )}


      {showModal && <AssignmentModal onClose={() => setShowModal(false)} onSave={handleCreate} />}
    </div>
  )
}
