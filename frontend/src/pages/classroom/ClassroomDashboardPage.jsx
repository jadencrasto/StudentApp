import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useLocation } from 'react-router-dom'
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
  const [authError, setAuthError] = useState(null)   // 'not_connected' | 'expired' | null
  const location = useLocation()

  useEffect(() => {
    try {
      const cachedCourses = localStorage.getItem(CLASSROOM_COURSES_KEY)
      const cachedEvents = localStorage.getItem(CLASSROOM_EVENTS_KEY)
      const cachedMaterials = localStorage.getItem(CLASSROOM_MATERIALS_KEY)
      const cachedLastSync = localStorage.getItem(CLASSROOM_LAST_SYNC_KEY)

      if (cachedCourses) {
        setCourses(JSON.parse(cachedCourses))
      }
      if (cachedEvents) {
        setEvents(JSON.parse(cachedEvents))
      }
      if (cachedMaterials) {
        setMaterials(JSON.parse(cachedMaterials))
      }
      if (cachedLastSync) {
        const parsed = Number(cachedLastSync)
        if (Number.isFinite(parsed) && parsed > 0) {
          setLastSyncedAt(parsed)
        }
      }
    } catch {
      localStorage.removeItem(CLASSROOM_COURSES_KEY)
      localStorage.removeItem(CLASSROOM_EVENTS_KEY)
      localStorage.removeItem(CLASSROOM_MATERIALS_KEY)
      localStorage.removeItem(CLASSROOM_LAST_SYNC_KEY)
    }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('connected') === '1') {
      toast.success('Google Classroom connected')
    }
  }, [location.search])

  async function connectGoogle() {
    try {
      const token = localStorage.getItem('sais_token')
      if (!token) {
        toast.error('Please login first')
        return
      }
      const apiBase = (client.defaults.baseURL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
      // OAuth routes are mounted at root level (not under /api/v1), extract just the origin
      const apiOrigin = new URL(apiBase).origin
      window.location.href = `${apiOrigin}/auth/google/connect?token=${encodeURIComponent(token)}`
    } catch {
      toast.error('Failed to start Google OAuth')
    }
  }

  const loadClassroom = useCallback(async ({ silent = false } = {}) => {
    setLoading(true)
    try {
      // Check connection status first to avoid noisy errors when not connected
      const statusResp = await client.get('/classroom/status')
      if (!statusResp.data?.connected) {
        setAuthError('not_connected')
        return
      }

      // Use combined sync endpoint — fetches courses once, then
      // events + materials in one pass (avoids triple Google API roundtrip)
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
      const detail = error.response?.data?.detail || ''
      if (status === 404 || detail.toLowerCase().includes('not connected')) {
        setAuthError('not_connected')
      } else if (status === 401 || status === 403 || detail.toLowerCase().includes('expired') || detail.toLowerCase().includes('revoked')) {
        setAuthError('expired')
      } else {
        if (!silent) toast.error(detail || 'Failed to load Classroom data')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  async function disconnectGoogle() {
    try {
      await client.delete('/classroom/disconnect')
      setAuthError('not_connected')
      setCourses([])
      setEvents([])
      setMaterials([])
      localStorage.removeItem(CLASSROOM_COURSES_KEY)
      localStorage.removeItem(CLASSROOM_EVENTS_KEY)
      localStorage.removeItem(CLASSROOM_MATERIALS_KEY)
      localStorage.removeItem(CLASSROOM_LAST_SYNC_KEY)
      toast.success('Google account disconnected — click Connect to reauthorize')
    } catch {
      toast.error('Failed to disconnect Google account')
    }
  }

  useEffect(() => {
    loadClassroom({ silent: true })
  }, [loadClassroom])

  const assignments = useMemo(() => {
    const isNineAClassroom = (courseName) => {
      const text = String(courseName || '').toLowerCase().trim()
      return text.includes('9a classroom') || text === '9a'
    }

    return events.filter((event) => event.type === 'Assignment' && !isNineAClassroom(event.course))
  }, [events])
  const categorizedAssignments = useMemo(() => {
    const assignedWithDueDate = []
    const assignedWithoutDueDate = []
    const submitted = []
    const missing = []

    const now = Date.now()
    const isNineAClassroom = (courseName) => {
      const text = String(courseName || '').toLowerCase().trim()
      return text.includes('9a classroom') || text === '9a'
    }

    const getEffectiveDueDate = (assignment) => {
      if (isNineAClassroom(assignment.course)) return null
      return assignment.due_date || null
    }

    const toTs = (value) => {
      if (!value) return null
      const ts = new Date(value).getTime()
      return Number.isFinite(ts) ? ts : null
    }

    const deriveStatus = (assignment) => {
      const explicit = (assignment.submission_status || '').toLowerCase()
      if (['assigned', 'submitted', 'late_submit', 'missing'].includes(explicit)) {
        return explicit
      }

      const state = (assignment.submission_state || '').toUpperCase()
      const dueTs = toTs(getEffectiveDueDate(assignment))
      const isPastDue = dueTs ? dueTs < now : false

      if (state === 'TURNED_IN' || state === 'RETURNED') return 'submitted'
      if (state === 'RECLAIMED_BY_STUDENT') return isPastDue ? 'missing' : 'assigned'
      if (state === 'NEW' || state === 'CREATED') return isPastDue ? 'missing' : 'assigned'
      return 'assigned'
    }

    const sortByDueThenPosted = (items) => items.sort((a, b) => {
      const aDue = toTs(a.due_date) ?? Number.MAX_SAFE_INTEGER
      const bDue = toTs(b.due_date) ?? Number.MAX_SAFE_INTEGER
      if (aDue !== bDue) return aDue - bDue
      const aPosted = toTs(a.posted_at) ?? 0
      const bPosted = toTs(b.posted_at) ?? 0
      return bPosted - aPosted
    })

    const sortByPostedDesc = (items) => items.sort((a, b) => {
      const aPosted = toTs(a.posted_at) ?? 0
      const bPosted = toTs(b.posted_at) ?? 0
      return bPosted - aPosted
    })

    const sortByMissingPriority = (items) => items.sort((a, b) => {
      const aDue = toTs(a.due_date) ?? 0
      const bDue = toTs(b.due_date) ?? 0
      return bDue - aDue
    })

    for (const assignment of assignments) {
      const status = deriveStatus(assignment)

      if (status === 'submitted' || status === 'late_submit') {
        submitted.push(assignment)
      } else if (status === 'missing') {
        missing.push(assignment)
      } else if (getEffectiveDueDate(assignment)) {
        assignedWithDueDate.push(assignment)
      } else {
        assignedWithoutDueDate.push(assignment)
      }
    }

    sortByDueThenPosted(assignedWithDueDate)
    sortByPostedDesc(assignedWithoutDueDate)
    sortByPostedDesc(submitted)
    sortByMissingPriority(missing)

    return {
      assignedWithDueDate,
      assignedWithoutDueDate,
      submitted,
      missing,
    }
  }, [assignments])

  const assignmentGroups = useMemo(() => ([
    { key: 'assignedWithDueDate', title: 'Assigned With Due Date', items: categorizedAssignments.assignedWithDueDate },
    { key: 'assignedWithoutDueDate', title: 'Assigned Without Due Date', items: categorizedAssignments.assignedWithoutDueDate },
    { key: 'submitted', title: 'Submitted', items: categorizedAssignments.submitted },
    { key: 'missing', title: 'Missing', items: categorizedAssignments.missing },
  ]), [categorizedAssignments])

  const lastSyncedLabel = useMemo(() => {
    if (!lastSyncedAt) return 'Not synced yet'
    return new Date(lastSyncedAt).toLocaleString()
  }, [lastSyncedAt])

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <h1 className="font-display text-3xl text-white mb-2">Google Classroom</h1>
        <p className="text-slate-400 mb-6">Connect Google and view your courses, assignments, announcements.</p>
      </motion.div>

      {/* Auth error banner */}
      {authError && (
        <div className="mb-6 flex items-center justify-between bg-emerald-400/10 border border-emerald-400/30 rounded-xl px-5 py-4">
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

      <div className="flex gap-3 mb-6 flex-wrap">
        <button onClick={connectGoogle} className="px-4 py-2 bg-emerald-400 text-slate-900 rounded-xl font-semibold hover:bg-emerald-300 text-sm">
          {courses.length ? 'Reconnect Google' : 'Connect Google Classroom'}
        </button>
        <button onClick={loadClassroom} disabled={loading} className="px-4 py-2 bg-slate-800 border border-slate-700 text-slate-100 rounded-xl hover:bg-slate-700 disabled:opacity-50 text-sm">
          {loading ? 'Syncing...' : 'Sync Data'}
        </button>
        {courses.length > 0 && (
          <button onClick={disconnectGoogle} className="px-4 py-2 bg-slate-900 border border-red-900/50 text-red-400 rounded-xl hover:bg-red-900/20 text-sm transition-all">
            Disconnect
          </button>
        )}
      </div>
      <p className="text-slate-500 text-sm mb-6">Last synced: {lastSyncedLabel}</p>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15 }}
        className="grid grid-cols-1 lg:grid-cols-2 gap-6"
      >
        <div className="bg-black/40 border border-white/10 rounded-2xl overflow-hidden backdrop-blur-md">
          <h2 className="text-white font-semibold mb-3">Courses</h2>
          <div className="space-y-2">
            {courses.map((course, i) => (
              <motion.div
                key={course.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: 0.2 + i * 0.03 }}
                className="p-3 bg-slate-800/70 rounded-lg text-sm text-slate-200 hover:bg-slate-800 transition-colors"
              >
                {course.name}
              </motion.div>
            ))}
            {!courses.length && <p className="text-slate-500 text-sm">No courses loaded.</p>}
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
          <h2 className="text-white font-semibold mb-3">Assignments</h2>
          <div className="space-y-4">
            {assignmentGroups.map((group) => (
              <div key={group.key} className="border border-slate-800 rounded-xl p-3 bg-slate-900/60">
                <p className="text-slate-300 text-xs font-semibold uppercase tracking-wider mb-2">
                  {group.title} ({group.items.length})
                </p>
                <div className="space-y-2">
                  {group.items.map((event, idx) => (
                    <div key={`${group.key}-${event.title}-${idx}`} className="p-3 bg-slate-800/70 rounded-lg text-sm">
                      <p className="text-slate-200 font-medium">{event.title}</p>
                      <p className="text-slate-400 text-xs">{event.course}</p>
                      <p className="text-slate-400 text-xs">Posted: {event.posted_at ? new Date(event.posted_at).toLocaleDateString() : 'Unknown'}</p>
                      <p className="text-slate-400 text-xs">Due: {(String(event.course || '').toLowerCase().includes('9a classroom') || String(event.course || '').toLowerCase().trim() === '9a') ? 'No due date' : (event.due_date || 'No due date')}</p>
                      {(event.submission_status === 'late_submit' || event.submission_status === 'submitted') && (
                        <p className="text-slate-400 text-xs">Status: {event.submission_status === 'late_submit' ? 'Late submit' : 'Submitted'}</p>
                      )}
                      {event.attachments && event.attachments.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {event.attachments.map((att, ai) => (
                            <a
                              key={ai}
                              href={att.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-700/60 text-emerald-300 text-xs rounded hover:bg-slate-600/80 transition-colors"
                              title={att.title}
                            >
                              {att.type === 'drive' && '📄'}
                              {att.type === 'youtube' && '▶️'}
                              {att.type === 'link' && '🔗'}
                              {att.type === 'form' && '📝'}
                              <span className="max-w-[120px] truncate">{att.title}</span>
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                  {!group.items.length && <p className="text-slate-500 text-sm">No items.</p>}
                </div>
              </div>
            ))}

            {!assignments.length && <p className="text-slate-500 text-sm">No assignments loaded.</p>}
          </div>
        </div>
      </motion.div>

      {/* Course Materials / Documents */}
      <div className="mt-6 bg-slate-900 border border-slate-800 rounded-2xl p-5">
        <h2 className="text-white font-semibold mb-3">Course Materials &amp; Documents</h2>
        <div className="space-y-3">
          {materials.length > 0 ? materials.map((mat, idx) => (
            <div key={mat.id || idx} className="p-4 bg-slate-800/70 rounded-lg">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-slate-200 font-medium text-sm">{mat.title}</p>
                  <p className="text-slate-400 text-xs mt-0.5">{mat.course}</p>
                  {mat.description && (
                    <p className="text-slate-500 text-xs mt-1 line-clamp-2">{mat.description}</p>
                  )}
                  <p className="text-slate-500 text-xs mt-1">
                    Posted: {mat.creation_time ? new Date(mat.creation_time).toLocaleDateString() : 'Unknown'}
                  </p>
                </div>
                {mat.alternate_link && (
                  <a
                    href={mat.alternate_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 px-3 py-1.5 bg-amber-400/10 text-amber-300 text-xs font-medium rounded-lg hover:bg-amber-400/20 transition-colors"
                  >
                    Open
                  </a>
                )}
              </div>
              {mat.attachments && mat.attachments.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {mat.attachments.map((att, ai) => (
                    <a
                      key={ai}
                      href={att.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-slate-700/60 text-amber-300 text-xs rounded-lg hover:bg-slate-600/80 transition-colors"
                      title={att.title}
                    >
                      {att.type === 'drive' && '📄'}
                      {att.type === 'youtube' && '▶️'}
                      {att.type === 'link' && '🔗'}
                      {att.type === 'form' && '📝'}
                      <span className="max-w-[180px] truncate">{att.title}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          )) : (
            <p className="text-slate-500 text-sm">No materials loaded. Connect Google Classroom to see course materials.</p>
          )}
        </div>
      </div>
    </div>
  )
}
