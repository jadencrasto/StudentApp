import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useLocation } from 'react-router-dom'
import {
  FileText, Link as LinkIcon, Youtube, FileQuestion,
  Calendar, ExternalLink, GraduationCap, ChevronDown,
} from 'lucide-react'
import client from '../../api/client'
import toast from 'react-hot-toast'

const CLASSROOM_COURSES_KEY = 'sais_classroom_courses'
const CLASSROOM_EVENTS_KEY = 'sais_classroom_events'
const CLASSROOM_MATERIALS_KEY = 'sais_classroom_materials'
const CLASSROOM_LAST_SYNC_KEY = 'sais_classroom_last_sync'

export default function ClassroomDashboardPage() {
  const [courses, setCourses] = useState([])
  const [events, setEvents] = useState([])
  const [materials, setMaterials] = useState([])
  const [lastSyncedAt, setLastSyncedAt] = useState(null)
  const [loading, setLoading] = useState(false)
  const [authError, setAuthError] = useState(null) // 'not_connected' | 'expired' | null
  const [selectedCourse, setSelectedCourse] = useState('All Classrooms')
  const location = useLocation()

  // ── Load cache on mount ─────────────────────────────────
  useEffect(() => {
    try {
      const cc = localStorage.getItem(CLASSROOM_COURSES_KEY)
      const ce = localStorage.getItem(CLASSROOM_EVENTS_KEY)
      const cm = localStorage.getItem(CLASSROOM_MATERIALS_KEY)
      const cs = localStorage.getItem(CLASSROOM_LAST_SYNC_KEY)
      if (cc) setCourses(JSON.parse(cc))
      if (ce) setEvents(JSON.parse(ce))
      if (cm) setMaterials(JSON.parse(cm))
      if (cs) {
        const parsed = Number(cs)
        if (Number.isFinite(parsed) && parsed > 0) setLastSyncedAt(parsed)
      }
    } catch {
      localStorage.removeItem(CLASSROOM_COURSES_KEY)
      localStorage.removeItem(CLASSROOM_EVENTS_KEY)
      localStorage.removeItem(CLASSROOM_MATERIALS_KEY)
      localStorage.removeItem(CLASSROOM_LAST_SYNC_KEY)
    }
  }, [])

  // ── OAuth redirect toast ────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('connected') === '1') toast.success('Google Classroom connected')
  }, [location.search])

  // ── Auth helpers ────────────────────────────────────────
  async function connectGoogle() {
    try {
      const apiBase = client.defaults.baseURL || '/api/v1'
      const origin = apiBase.startsWith('http') ? new URL(apiBase).origin : window.location.origin
      window.location.href = `${origin}/auth/google/connect`
    } catch {
      toast.error('Failed to start Google OAuth')
    }
  }

  const loadClassroom = useCallback(async ({ silent = false } = {}) => {
    setLoading(true)
    try {
      const statusResp = await client.get('/classroom/status')
      if (!statusResp.data?.connected) { setAuthError('not_connected'); return }

      const syncResp = await client.get('/classroom/sync', { timeout: 300000 })
      const syncData = syncResp.data || {}
      const nextCourses = syncData.courses || []
      const nextEvents = syncData.events || []
      const nextMaterials = syncData.materials || []
      const syncedAt = Date.now()

      setCourses(nextCourses)
      setEvents(nextEvents)
      setMaterials(nextMaterials)
      setLastSyncedAt(syncedAt)
      setAuthError(null)
      localStorage.setItem(CLASSROOM_COURSES_KEY, JSON.stringify(nextCourses))
      localStorage.setItem(CLASSROOM_EVENTS_KEY, JSON.stringify(nextEvents))
      localStorage.setItem(CLASSROOM_MATERIALS_KEY, JSON.stringify(nextMaterials))
      localStorage.setItem(CLASSROOM_LAST_SYNC_KEY, String(syncedAt))
    } catch (error) {
      const status = error.response?.status
      const detail = (error.response?.data?.detail || '').toLowerCase()
      if (status === 404 || detail.includes('not connected')) {
        setAuthError('not_connected')
      } else if (status === 401 || status === 403 || detail.includes('expired') || detail.includes('revoked')) {
        setAuthError('expired')
      } else {
        if (!silent) toast.error(error.response?.data?.detail || 'Failed to load Classroom data')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  async function disconnectGoogle() {
    try {
      await client.delete('/classroom/disconnect')
      setAuthError('not_connected')
      setCourses([]); setEvents([]); setMaterials([])
      localStorage.removeItem(CLASSROOM_COURSES_KEY)
      localStorage.removeItem(CLASSROOM_EVENTS_KEY)
      localStorage.removeItem(CLASSROOM_MATERIALS_KEY)
      localStorage.removeItem(CLASSROOM_LAST_SYNC_KEY)
      toast.success('Google account disconnected — click Connect to reauthorize')
    } catch {
      toast.error('Failed to disconnect Google account')
    }
  }

  useEffect(() => { loadClassroom({ silent: true }) }, [loadClassroom])

  // ── Data helpers ────────────────────────────────────────
  const isNineAClassroom = (courseName) => {
    const text = String(courseName || '').toLowerCase().trim()
    return text.includes('9a classroom') || text === '9a'
  }

  const assignments = useMemo(() =>
    events.filter(e => e.type === 'Assignment' && !isNineAClassroom(e.course))
    , [events])

  const courseNames = useMemo(() => {
    const names = new Set(assignments.map(a => a.course).filter(Boolean))
    return ['All Classrooms', ...Array.from(names).sort()]
  }, [assignments])

  const filteredAssignments = useMemo(() => {
    if (selectedCourse === 'All Classrooms') return assignments
    return assignments.filter(a => a.course === selectedCourse)
  }, [assignments, selectedCourse])

  const categorizedAssignments = useMemo(() => {
    const assignedWithDueDate = []
    const assignedWithoutDueDate = []
    const submitted = []
    const missing = []
    const now = Date.now()

    const getEffectiveDueDate = a => isNineAClassroom(a.course) ? null : (a.due_date || null)
    const toTs = v => { if (!v) return null; const t = new Date(v).getTime(); return Number.isFinite(t) ? t : null }

    const deriveStatus = a => {
      const explicit = (a.submission_status || '').toLowerCase()
      if (['assigned', 'submitted', 'late_submit', 'missing'].includes(explicit)) return explicit
      const state = (a.submission_state || '').toUpperCase()
      const dueTs = toTs(getEffectiveDueDate(a))
      const pastDue = dueTs ? dueTs < now : false
      if (state === 'TURNED_IN' || state === 'RETURNED') return 'submitted'
      if (state === 'RECLAIMED_BY_STUDENT') return pastDue ? 'missing' : 'assigned'
      if (state === 'NEW' || state === 'CREATED') return pastDue ? 'missing' : 'assigned'
      return 'assigned'
    }

    const sortByDueThenPosted = items => items.sort((a, b) => {
      const aDue = toTs(a.due_date) ?? Number.MAX_SAFE_INTEGER
      const bDue = toTs(b.due_date) ?? Number.MAX_SAFE_INTEGER
      if (aDue !== bDue) return aDue - bDue
      return (toTs(b.posted_at) ?? 0) - (toTs(a.posted_at) ?? 0)
    })
    const sortByPostedDesc = items => items.sort((a, b) => (toTs(b.posted_at) ?? 0) - (toTs(a.posted_at) ?? 0))
    const sortByMissing = items => items.sort((a, b) => (toTs(b.due_date) ?? 0) - (toTs(a.due_date) ?? 0))

    for (const a of filteredAssignments) {
      const status = deriveStatus(a)
      if (status === 'submitted' || status === 'late_submit') submitted.push(a)
      else if (status === 'missing') missing.push(a)
      else if (getEffectiveDueDate(a)) assignedWithDueDate.push(a)
      else assignedWithoutDueDate.push(a)
    }

    sortByDueThenPosted(assignedWithDueDate)
    sortByPostedDesc(assignedWithoutDueDate)
    sortByPostedDesc(submitted)
    sortByMissing(missing)

    return { assignedWithDueDate, assignedWithoutDueDate, submitted, missing }
  }, [filteredAssignments])

  const assignmentGroups = useMemo(() => [
    { key: 'assignedWithDueDate', title: 'Assigned With Due Date', items: categorizedAssignments.assignedWithDueDate },
    { key: 'assignedWithoutDueDate', title: 'Assigned Without Due Date', items: categorizedAssignments.assignedWithoutDueDate },
    { key: 'submitted', title: 'Submitted', items: categorizedAssignments.submitted },
    { key: 'missing', title: 'Missing', items: categorizedAssignments.missing },
  ], [categorizedAssignments])

  const lastSyncedLabel = useMemo(() =>
    lastSyncedAt ? new Date(lastSyncedAt).toLocaleString() : 'Not synced yet'
    , [lastSyncedAt])

  // ── Render ──────────────────────────────────────────────
  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">

      {/* ── Page Header ───────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-2"
      >
        <div>
          <h1 className="font-display text-3xl text-white mb-1">Classroom Assignments</h1>
          <p className="text-slate-400 text-sm">Connect Google and view your courses, assignments, and announcements.</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
          <button
            onClick={connectGoogle}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold rounded-xl text-sm transition-all"
          >
            {courses.length ? 'Reconnect' : 'Connect Google'}
          </button>
          <button
            onClick={loadClassroom}
            disabled={loading}
            className="px-4 py-2 bg-slate-800 border border-slate-700 text-slate-100 rounded-xl hover:bg-slate-700 disabled:opacity-50 text-sm transition-all"
          >
            {loading ? 'Syncing…' : 'Sync Data'}
          </button>
          {courses.length > 0 && (
            <button
              onClick={disconnectGoogle}
              className="px-4 py-2 bg-slate-900 border border-red-900/50 text-red-400 rounded-xl hover:bg-red-900/20 text-sm transition-all"
            >
              Disconnect
            </button>
          )}
        </div>
      </motion.div>

      <p className="text-slate-500 text-xs mb-6">Last synced: {lastSyncedLabel}</p>

      {/* ── Auth error banner ──────────────────────────────── */}
      {authError && (
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-emerald-400/10 border border-emerald-400/30 rounded-xl px-5 py-4">
          <div>
            <p className="text-emerald-300 font-semibold text-sm">
              {authError === 'expired'
                ? 'Your Google credentials expired or were revoked.'
                : 'Google Classroom is not connected.'}
            </p>
            <p className="text-emerald-400/70 text-xs mt-0.5">
              {authError === 'expired'
                ? 'Click Reconnect to re-authorize with updated permissions.'
                : 'Connect your Google account to sync courses and assignments.'}
            </p>
          </div>
          <button
            onClick={connectGoogle}
            className="ml-4 px-4 py-2 bg-emerald-400 text-slate-900 rounded-xl font-bold text-sm hover:bg-emerald-300 transition-all flex-shrink-0"
          >
            {authError === 'expired' ? 'Reconnect Google' : 'Connect Google'}
          </button>
        </div>
      )}

      {/* ── Course Selector Dropdown ───────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
        className="mb-6"
      >
        <label className="flex items-center gap-1.5 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <GraduationCap size={13} className="text-emerald-400" />
          Select Classroom
        </label>
        <div className="relative w-full sm:max-w-sm">
          <select
            value={selectedCourse}
            onChange={e => setSelectedCourse(e.target.value)}
            className="w-full bg-black/50 text-slate-200 border border-emerald-500/30 focus:border-emerald-500/60 focus:ring-2 focus:ring-emerald-500/20 rounded-xl pl-4 pr-10 py-2.5 text-sm appearance-none outline-none transition-all cursor-pointer"
          >
            {courseNames.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
          <ChevronDown size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-emerald-400" />
        </div>

        {assignments.length > 0 && (
          <p className="mt-2 text-slate-500 text-xs">
            Showing{' '}
            <span className="text-emerald-400 font-semibold">{filteredAssignments.length}</span>{' '}
            assignment{filteredAssignments.length !== 1 ? 's' : ''} from{' '}
            <span className="text-slate-300">{selectedCourse}</span>
          </p>
        )}
      </motion.div>

      {/* ── Assignments Panel (full width) ─────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.15 }}
      >
        {assignments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center bg-black/20 rounded-2xl border border-white/5">
            <GraduationCap size={52} className="text-slate-700 mb-4" />
            <p className="text-slate-400 font-medium mb-1">No assignments loaded</p>
            <p className="text-slate-600 text-sm">
              Click <strong className="text-slate-400">Sync Data</strong> to import from Google Classroom.
            </p>
          </div>
        ) : filteredAssignments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center bg-black/20 rounded-2xl border border-white/5">
            <GraduationCap size={52} className="text-slate-700 mb-4" />
            <p className="text-slate-400 font-medium mb-1">No assignments found for this classroom</p>
            <button
              onClick={() => setSelectedCourse('All Classrooms')}
              className="mt-3 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition-colors"
            >
              Show All Classrooms
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            {assignmentGroups.filter(g => g.items.length > 0).map(group => (
              <div key={group.key} className="bg-black/40 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-sm">

                {/* Group header */}
                <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02]">
                  <p className="text-slate-300 text-xs font-bold uppercase tracking-widest flex items-center gap-2">
                    {group.title}
                    <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-full text-[10px] font-semibold normal-case tracking-normal">
                      {group.items.length}
                    </span>
                  </p>
                </div>

                {/* Cards */}
                <div className="divide-y divide-white/5">
                  {group.items.map((event, idx) => (
                    <motion.div
                      key={`${group.key}-${event.title}-${idx}`}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, delay: idx * 0.02 }}
                      className="p-4 md:p-5 hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <p className="text-white font-semibold text-sm leading-snug mb-2">{event.title}</p>

                          <div className="flex items-center flex-wrap gap-2 mb-2">
                            <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-full text-xs font-medium">
                              {event.course}
                            </span>
                            {event.posted_at && (
                              <span className="flex items-center gap-1 text-slate-500 text-xs">
                                <Calendar size={11} />
                                Posted: {new Date(event.posted_at).toLocaleDateString()}
                              </span>
                            )}
                            {!isNineAClassroom(event.course) && event.due_date && (
                              <span className="flex items-center gap-1 text-slate-500 text-xs">
                                <Calendar size={11} />
                                Due: {event.due_date}
                              </span>
                            )}
                            {(event.submission_status === 'late_submit' || event.submission_status === 'submitted') && (
                              <span className="px-2 py-0.5 bg-slate-700/60 text-slate-400 rounded-full text-xs">
                                {event.submission_status === 'late_submit' ? 'Late Submit' : 'Submitted'}
                              </span>
                            )}
                          </div>

                          {event.attachments && event.attachments.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {event.attachments.map((att, ai) => (
                                <a
                                  key={ai}
                                  href={att.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title={att.title}
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-slate-700/60 text-emerald-400 text-xs rounded-lg hover:bg-slate-600/80 transition-colors"
                                >
                                  {att.type === 'drive' && <FileText size={12} />}
                                  {att.type === 'youtube' && <Youtube size={12} />}
                                  {att.type === 'link' && <LinkIcon size={12} />}
                                  {att.type === 'form' && <FileQuestion size={12} />}
                                  <span className="max-w-[140px] truncate">{att.title}</span>
                                </a>
                              ))}
                            </div>
                          )}
                        </div>

                        {event.link && (
                          <a
                            href={event.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-emerald-400/10 hover:bg-emerald-400/20 border border-emerald-400/30 text-emerald-400 text-xs font-semibold rounded-xl transition-all"
                          >
                            Open <ExternalLink size={11} />
                          </a>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  )
}
