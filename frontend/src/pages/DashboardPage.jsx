import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { getAssignments } from '../api/assignments'
import { getSummary } from '../api/attendance'
import { getActivities } from '../api/activities'
import { getAlerts, refreshAlerts, markAlertRead } from '../api/alerts'
import { getMorningCheckin, getUnmarkedReminders, getEndOfDaySummary } from '../api/timetable'
import client from '../api/client'
import { useAuth } from '../hooks/useAuth'
import {
  format,
  differenceInDays,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  isSameMonth,
  isToday,
  addMonths,
  subMonths,
  startOfWeek,
  endOfWeek,
} from 'date-fns'
import { AlertTriangle, CheckCircle, BookOpen, CalendarCheck, Trophy, Bell, RefreshCw, ChevronRight } from 'lucide-react'
import { RadialBarChart, RadialBar, ResponsiveContainer } from 'recharts'
import toast from 'react-hot-toast'
import AlertsWidget from '../components/attendance/AlertsWidget'
import MorningCheckin from '../components/reminders/MorningCheckin'
import UnmarkedAlert from '../components/reminders/UnmarkedAlert'
import EndOfDaySummary from '../components/reminders/EndOfDaySummary'
import { StatSkeleton, CardSkeleton } from '../components/ui/animations'

const ease = [0.4, 0, 0.2, 1]

function StatCard({ title, value, sub, accent, icon: Icon, index = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.45, delay: 0.08 * index, ease }}
      whileHover={{ y: -3, transition: { duration: 0.2 } }}
      className="bg-white/[0.02] border border-white/10 hover:border-emerald-500/20 rounded-2xl p-5 flex items-center gap-4 cursor-default transition-all"
    >
      <motion.div
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.08 * index + 0.15, ease }}
        className={`w-12 h-12 rounded-xl flex items-center justify-center ${accent}`}
      >
        <Icon size={22} />
      </motion.div>
      <div>
        <motion.p
          key={value}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="text-2xl font-semibold text-white"
        >{value}</motion.p>
        <p className="text-sm font-medium text-slate-300">{title}</p>
        {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      </div>
    </motion.div>
  )
}

function AlertItem({ alert, onRead }) {
  const colors = { critical: 'border-red-400/30 bg-red-400/5 text-red-400', warning: 'border-amber-500/30 bg-amber-500/5 text-amber-400', info: 'border-blue-400/30 bg-blue-400/5 text-blue-400' }
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16, height: 0, marginBottom: 0, transition: { duration: 0.25 } }}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.98 }}
      className={`flex items-start gap-3 p-3 rounded-xl border ${colors[alert.severity]} cursor-pointer`}
      onClick={() => onRead(alert.id)}
    >
      <AlertTriangle size={15} className="mt-0.5 flex-shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{alert.title}</p>
        <p className="text-xs opacity-80 mt-0.5 line-clamp-2">{alert.message}</p>
      </div>
    </motion.div>
  )
}

function DeadlineItem({ a, index = 0 }) {
  const dateObj = a.deadline ? new Date(a.deadline) : null
  const daysLeft = dateObj && !isNaN(dateObj.getTime()) ? differenceInDays(dateObj, new Date()) : null
  const urgent = daysLeft !== null && daysLeft <= 2
  const dateLabel = dateObj && !isNaN(dateObj.getTime()) ? format(dateObj, 'MMM d') : null
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, delay: 0.04 * index, ease }}
      className="flex items-center gap-3 py-2.5 border-b border-white/5 last:border-0"
    >
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.04 * index + 0.2, type: 'spring', stiffness: 500 }}
        className={`w-2 h-2 rounded-full flex-shrink-0 ${urgent ? 'bg-red-400' : 'bg-emerald-400'}`}
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-200 truncate">{a.title}</p>
        <p className="text-xs text-slate-500">
          {a.subject || 'No subject'} · {a.task_type}
          {dateLabel && <span className="ml-1 text-slate-400">· Due {dateLabel}</span>}
        </p>
      </div>
      <span className={`text-xs font-mono font-medium flex-shrink-0 ${urgent ? 'text-red-400' : 'text-emerald-400'}`}>
        {daysLeft === null ? 'No date' : daysLeft < 0 ? 'Overdue' : daysLeft === 0 ? 'Today' : daysLeft === 1 ? 'Tomorrow' : `${daysLeft}d left`}
      </span>
    </motion.div>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [assignments, setAssignments] = useState([])
  const [summaries, setSummaries] = useState([])
  const [activities, setActivities] = useState([])
  const [alerts, setAlerts] = useState([])
  const [morningCheckin, setMorningCheckin] = useState(null)
  const [unmarkedReminder, setUnmarkedReminder] = useState(null)
  const [endOfDaySummary, setEndOfDaySummary] = useState(null)
  const [academicEvents, setAcademicEvents] = useState([])
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [calendarAnchored, setCalendarAnchored] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Load critical data first (fast endpoints)
    Promise.allSettled([
      getAssignments().then(r => setAssignments(r.data)),
      getSummary().then(r => setSummaries(r.data)),
      getActivities().then(r => setActivities(r.data)),
      getAlerts(true).then(r => setAlerts(r.data)),
    ]).finally(() => setLoading(false))

    // Load timetable reminders (secondary priority, fire-and-forget)
    getMorningCheckin().then(r => setMorningCheckin(r.data)).catch(() => { })
    getUnmarkedReminders().then(r => setUnmarkedReminder(r.data)).catch(() => { })
    getEndOfDaySummary().then(r => setEndOfDaySummary(r.data)).catch(() => { })

    // Defer events loading (slowest endpoint — web scraping)
    const eventsTimer = setTimeout(() => {
      client.get('/events').catch(() => ({ data: [] }))
        .then(r => setAcademicEvents(Array.isArray(r?.data) ? r.data : []))
    }, 100)
    return () => clearTimeout(eventsTimer)
  }, [])

  useEffect(() => {
    if (calendarAnchored) return

    const today = new Date()
    const candidates = []

    academicEvents.forEach((event) => {
      const raw = String(event?.start || event?.date || '').trim()
      const normalized = raw.length >= 10 ? raw.slice(0, 10) : raw
      if (!normalized) return
      const parsed = new Date(normalized)
      if (!isNaN(parsed.getTime())) candidates.push(parsed)
    })

    assignments.forEach((assignment) => {
      if (!assignment?.deadline) return
      const parsed = new Date(assignment.deadline)
      if (!isNaN(parsed.getTime())) candidates.push(parsed)
    })

    if (candidates.length === 0) return

    let nearest = candidates[0]
    let nearestDelta = Math.abs(candidates[0].getTime() - today.getTime())
    for (let i = 1; i < candidates.length; i += 1) {
      const delta = Math.abs(candidates[i].getTime() - today.getTime())
      if (delta < nearestDelta) {
        nearest = candidates[i]
        nearestDelta = delta
      }
    }

    setCurrentMonth(nearest)
    setCalendarAnchored(true)
  }, [academicEvents, assignments, calendarAnchored])

  async function handleRefreshAlerts() {
    setRefreshing(true)
    try {
      const { data } = await refreshAlerts()
      const fresh = await getAlerts(true)
      setAlerts(fresh.data)
      toast.success(`Generated ${data.generated} new alert${data.generated !== 1 ? 's' : ''}`)
    } catch { toast.error('Failed to refresh alerts') }
    finally { setRefreshing(false) }
  }

  async function handleReadAlert(id) {
    await markAlertRead(id).catch(() => { })
    setAlerts(prev => prev.filter(a => a.id !== id))
  }

  const avgAttendance = summaries.length
    ? Math.round(summaries.reduce((s, x) => s + x.attendance_percentage, 0) / summaries.length)
    : 0
  const lowAttendance = summaries.filter(s => s.below_threshold).length
  const conflictCount = activities.filter(a => a.has_conflict).length
  const activeAssignments = assignments.filter(a => a.status !== 'completed')
  const assignmentsForPanel = [...activeAssignments].sort((a, b) => {
    const aHasDeadline = Boolean(a.deadline)
    const bHasDeadline = Boolean(b.deadline)

    if (aHasDeadline && bHasDeadline) {
      return new Date(a.deadline) - new Date(b.deadline)
    }
    if (aHasDeadline !== bHasDeadline) {
      return aHasDeadline ? -1 : 1
    }

    return new Date(b.created_at) - new Date(a.created_at)
  })

  const monthStart = startOfMonth(currentMonth)
  const monthEnd = endOfMonth(monthStart)
  const calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 })
  const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })
  const calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd })

  const eventsByDate = {}

  function normalizeEventType(event) {
    const typeText = String(event?.type || '').toLowerCase()
    const titleText = String(event?.title || event?.event_name || '').toLowerCase()
    const combined = `${typeText} ${titleText}`

    if (combined.includes('exam') || combined.includes('ese') || combined.includes('mse')) return 'exam'
    if (combined.includes('holiday') || combined.includes('break')) return 'holiday'
    if (combined.includes('semester') || combined.includes('sem')) return 'semester'
    return 'academic'
  }

  academicEvents.forEach((event) => {
    const rawDay = String(event?.start || event?.date || '').trim()
    const day = rawDay.length >= 10 ? rawDay.slice(0, 10) : rawDay
    if (!day) return
    if (!eventsByDate[day]) eventsByDate[day] = []
    eventsByDate[day].push({
      title: event?.title || event?.event_name || 'Academic Event',
      type: normalizeEventType(event),
    })
  })

  assignments.forEach((assignment) => {
    if (!assignment?.deadline) return
    const key = format(new Date(assignment.deadline + 'T00:00:00'), 'yyyy-MM-dd')
    if (!eventsByDate[key]) eventsByDate[key] = []
    eventsByDate[key].push({
      title: assignment.title,
      type: 'assignment',
    })
  })

  activities.forEach((activity) => {
    if (!activity?.activity_date) return
    const key = format(new Date(activity.activity_date + 'T00:00:00'), 'yyyy-MM-dd')
    if (!eventsByDate[key]) eventsByDate[key] = []
    eventsByDate[key].push({
      title: activity.title,
      type: 'activity',
    })
  })

  const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  function getEventPillClass(type) {
    if (type === 'activity')   return 'bg-blue-500/15 text-blue-300 border border-blue-500/20'
    if (type === 'assignment') return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
    if (type === 'exam')       return 'bg-red-400/15 text-red-300 border border-red-400/20'
    if (type === 'holiday')    return 'bg-emerald-400/15 text-emerald-300 border border-emerald-400/20'
    if (type === 'semester')   return 'bg-blue-400/15 text-blue-300 border border-blue-400/20'
    return 'bg-slate-700/60 text-slate-300 border border-slate-600/40'
  }

  return (
    <div className="p-8">
      {loading ? (
        <div className="space-y-8">
          {/* Skeleton header */}
          <div>
            <div className="skeleton h-8 w-64 mb-2" />
            <div className="skeleton h-4 w-40" />
          </div>
          {/* Skeleton stat cards */}
          <div className="grid grid-cols-4 gap-4">
            <StatSkeleton /><StatSkeleton /><StatSkeleton /><StatSkeleton />
          </div>
          {/* Skeleton panels */}
          <div className="grid grid-cols-3 gap-6">
            <CardSkeleton className="col-span-2" />
            <CardSkeleton />
          </div>
        </div>
      ) : (
      <>
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease }}
        className="mb-8"
      >
        <h1 className="font-display text-3xl text-white">
          Good {new Date().getHours() < 12 ? 'morning' : 'afternoon'},{' '}
          <span className="text-emerald-400">{user?.full_name?.split(' ')[0] || user?.username}</span>
        </h1>
        <p className="text-slate-400 mt-1">{format(new Date(), 'EEEE, MMMM d, yyyy')}</p>
      </motion.div>

      <MorningCheckin data={morningCheckin} />
      <UnmarkedAlert data={unmarkedReminder} />
      <EndOfDaySummary data={endOfDaySummary} />

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard index={0} title="Open Assignments" value={activeAssignments.length} sub="Including new drafts" accent="bg-emerald-500/10 text-emerald-400" icon={BookOpen} />
        <StatCard index={1} title="Avg Attendance" value={`${avgAttendance}%`} sub={lowAttendance > 0 ? `${lowAttendance} subject${lowAttendance > 1 ? 's' : ''} at risk` : 'All good'} accent="bg-emerald-400/10 text-emerald-400" icon={CalendarCheck} />
        <StatCard index={2} title="Activities" value={activities.length} sub={conflictCount > 0 ? `${conflictCount} conflict${conflictCount > 1 ? 's' : ''}` : 'No conflicts'} accent="bg-blue-400/10 text-blue-400" icon={Trophy} />
        <StatCard index={3} title="Alerts" value={alerts.length} sub="Unread" accent={alerts.length > 0 ? "bg-red-400/10 text-red-400" : "bg-white/5 text-gray-400"} icon={Bell} />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Upcoming assignments */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35, ease }}
          className="col-span-2 bg-white/[0.02] border border-white/10 hover:border-emerald-500/20 rounded-2xl p-6 transition-all"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg text-white">Assignments</h2>
            <Link to="/dashboard/assignments" className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1 transition-colors">View all <ChevronRight size={12} /></Link>
          </div>
          {assignmentsForPanel.length === 0
            ? <p className="text-sm text-slate-500 py-6 text-center">No assignments yet</p>
            : <div>{assignmentsForPanel.slice(0, 8).map((a, i) => <DeadlineItem key={a.id} a={a} index={i} />)}</div>
          }
        </motion.div>

        {/* Alerts panel */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4, ease }}
          className="bg-white/[0.02] border border-white/10 hover:border-emerald-500/20 rounded-2xl p-6 transition-all"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg text-white">AI Alerts</h2>
            <motion.button
              whileHover={{ rotate: 90 }}
              whileTap={{ scale: 0.9 }}
              onClick={handleRefreshAlerts}
              disabled={refreshing}
              className="p-1.5 rounded-lg text-gray-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            </motion.button>
          </div>
          {alerts.length === 0
            ? <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.5 }}
              className="flex flex-col items-center py-6 text-center"
            >
              <CheckCircle size={28} className="text-emerald-400 mb-2" />
              <p className="text-sm text-slate-400">All clear — no alerts right now</p>
            </motion.div>
            : <AnimatePresence mode="popLayout">
              <div className="space-y-2">
                {alerts.map(a => <AlertItem key={a.id} alert={a} onRead={handleReadAlert} />)}
              </div>
            </AnimatePresence>
          }
        </motion.div>

        {/* Attendance bar */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.45, ease }}
          className="col-span-2 bg-white/[0.02] border border-white/10 hover:border-emerald-500/20 rounded-2xl p-6 transition-all"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg text-white">Attendance by Subject</h2>
            <Link to="/dashboard/attendance" className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1 transition-colors">Manage <ChevronRight size={12} /></Link>
          </div>
          {summaries.length === 0
            ? <p className="text-sm text-slate-500 py-4 text-center">No subjects tracked yet</p>
            : <div className="space-y-3">
              {summaries.map((s, i) => (
                <motion.div
                  key={String(s.subject_id)}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.35, delay: 0.5 + i * 0.05, ease }}
                >
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-300">{s.subject_name}</span>
                    <span className={`font-mono font-medium ${s.below_threshold ? 'text-red-400' : 'text-emerald-400'}`}>{s.attendance_percentage}%</span>
                  </div>
                   <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${s.below_threshold ? 'bg-red-400' : 'bg-emerald-400'}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${s.attendance_percentage}%` }}
                      transition={{ duration: 0.8, delay: 0.55 + i * 0.05, ease }}
                    />
                  </div>
                </motion.div>
              ))}
            </div>
          }
        </motion.div>

        {/* Attendance Smart Alerts Widget */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5, ease }}
        >
          <AlertsWidget />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.55, ease }}
          className="col-span-2 bg-white/[0.02] border border-white/10 hover:border-emerald-500/20 rounded-2xl p-6 transition-all"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg text-white">Academic Calendar</h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
                className="px-3 py-1.5 text-xs rounded-lg bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10"
              >
                Prev
              </button>
              <span className="text-sm text-gray-300 min-w-[130px] text-center">{format(currentMonth, 'MMMM yyyy')}</span>
              <button
                onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
                className="px-3 py-1.5 text-xs rounded-lg bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10"
              >
                Next
              </button>
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-3 mb-3 flex-wrap">
            <span className="flex items-center gap-1.5 text-[10px] text-blue-300"><span className="w-2 h-2 rounded-full bg-blue-500/60 flex-shrink-0" />Activity</span>
            <span className="flex items-center gap-1.5 text-[10px] text-emerald-300"><span className="w-2 h-2 rounded-full bg-emerald-500/60 flex-shrink-0" />Assignment</span>
            <span className="flex items-center gap-1.5 text-[10px] text-red-300"><span className="w-2 h-2 rounded-full bg-red-400/60 flex-shrink-0" />Exam</span>
            <span className="flex items-center gap-1.5 text-[10px] text-slate-400"><span className="w-2 h-2 rounded-full bg-slate-500/60 flex-shrink-0" />Academic</span>
          </div>

          <div className="grid grid-cols-7 gap-2 mb-2">
            {weekdayLabels.map((label) => (
              <div key={label} className="text-xs text-slate-500 text-center py-1">{label}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-2">
            {calendarDays.map((day) => {
              const key = format(day, 'yyyy-MM-dd')
              const dayEvents = eventsByDate[key] || []
              const isInMonth = isSameMonth(day, monthStart)
              return (
                <div
                  key={key}
                  className={`min-h-[90px] rounded-xl border p-2 ${isInMonth ? 'border-white/10 bg-white/[0.03]' : 'border-white/5 bg-black/30'}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs ${isInMonth ? 'text-gray-300' : 'text-gray-600'}`}>{format(day, 'd')}</span>
                    {isToday(day) && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
                  </div>
                  <div className="space-y-1">
                    {dayEvents.slice(0, 2).map((event, idx) => (
                      <div key={`${key}-${idx}`} className={`text-[10px] leading-tight px-1.5 py-1 rounded ${getEventPillClass(event.type)}`}>
                        {event.title}
                      </div>
                    ))}
                    {dayEvents.length > 2 && (
                      <div className="text-[10px] text-slate-400 px-1">+{dayEvents.length - 2} more</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </motion.div>

        {/* Activities */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.6, ease }}
          className="bg-white/[0.02] border border-white/10 hover:border-emerald-500/20 rounded-2xl p-6 transition-all"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg text-white">Activities</h2>
            <Link to="/dashboard/activities" className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1">View all <ChevronRight size={12} /></Link>
          </div>
          {activities.length === 0
            ? <p className="text-sm text-slate-500 py-4 text-center">No activities added</p>
            : <div className="space-y-2">
              {activities.slice(0, 5).map((a, i) => (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: 0.65 + i * 0.04, ease }}
                  className="flex items-center gap-3 py-2"
                >
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${a.has_conflict ? 'bg-red-400' : 'bg-blue-400'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{a.title}</p>
                    <p className="text-xs text-slate-500">{a.activity_date ? format(new Date(a.activity_date), 'MMM d') : 'TBD'}{a.category ? ` · ${a.category}` : ''}</p>
                  </div>
                  {a.has_conflict && <span className="text-xs text-red-400 font-medium flex-shrink-0">Conflict</span>}
                </motion.div>
              ))}
            </div>
          }
        </motion.div>
      </div>
      </>
      )}
    </div>
  )
}

