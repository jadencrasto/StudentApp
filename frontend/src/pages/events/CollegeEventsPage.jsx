import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import client from '../../api/client'
import toast from 'react-hot-toast'

const STORAGE_KEY = 'sais_college_events_page_state'

export default function CollegeEventsPage() {
  const [colleges, setColleges] = useState([])
  const [college, setCollege] = useState('')
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)

  function savePageState(nextState) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState))
    } catch {
      // ignore storage errors
    }
  }

  function loadPageState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw)
      return {
        college: typeof parsed?.college === 'string' ? parsed.college : '',
        colleges: Array.isArray(parsed?.colleges) ? parsed.colleges : [],
        events: Array.isArray(parsed?.events) ? parsed.events : [],
      }
    } catch {
      return null
    }
  }

  async function fetchEventsForCollege(selectedCollege, silent = false) {
    if (!selectedCollege) return
    setLoading(true)
    try {
      const { data } = await client.get('/events', { params: { college: selectedCollege } })
      setEvents(data)
      savePageState({ college: selectedCollege, colleges, events: data })
      if (!silent) {
        toast.success(`Fetched ${data.length} events`)
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to fetch events')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const cached = loadPageState()
    if (cached) {
      if (cached.colleges.length) setColleges(cached.colleges)
      if (cached.college) setCollege(cached.college)
      if (cached.events.length) setEvents(cached.events)
    }

    client.get('/colleges')
      .then(({ data }) => {
        setColleges(data)

        const cachedCollege = cached?.college
        const hasCachedCollege = cachedCollege && data.some((c) => c.name === cachedCollege)
        const selectedCollege = hasCachedCollege ? cachedCollege : (data[0]?.name || '')

        if (data.length) {
          setCollege(selectedCollege)
          const hasCachedEvents = cached?.college === selectedCollege && Array.isArray(cached?.events) && cached.events.length > 0
          if (!hasCachedEvents) {
            fetchEventsForCollege(selectedCollege, true)
          }
        }
      })
      .catch(() => toast.error('Failed to load colleges'))
  }, [])

  useEffect(() => {
    savePageState({ college, colleges, events })
  }, [college, colleges, events])

  async function handleFetch() {
    await fetchEventsForCollege(college)
  }

  function handleCollegeChange(e) {
    const selectedCollege = e.target.value
    setCollege(selectedCollege)
    fetchEventsForCollege(selectedCollege, true)
  }

  function normalizeRow(event) {
    return {
      title: event?.title || event?.event_name || 'Academic Event',
      type: event?.type || event?.event_type || 'Notice',
      date: event?.start || event?.date || '',
      collegeName: event?.college || college,
      source: event?.source_url || null,
    }
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <h1 className="font-display text-3xl text-white mb-2">College Academic Events</h1>
        <p className="text-slate-400 mb-6">Select a college and fetch latest notices/exam/calendar events.</p>
      </motion.div>

      <div className="flex gap-3 mb-6">
        <select
          value={college}
          onChange={handleCollegeChange}
          className="bg-black/40 border border-white/10 rounded-xl px-4 py-2 text-white placeholder-gray-500 focus:border-emerald-500 focus:outline-none"
        >
          {colleges.map((c) => (
            <option key={c.name} value={c.name}>{c.name}</option>
          ))}
        </select>
        <button
          onClick={handleFetch}
          disabled={loading}
          className="px-4 py-2 bg-emerald-500 text-black rounded-xl font-semibold hover:bg-emerald-600 border border-emerald-500/20 disabled:opacity-50 transition-all"
        >
          {loading ? 'Fetching...' : 'Fetch Events'}
        </button>
      </div>

      <div className="space-y-3">
        {events.map((event, index) => (
          <motion.div
            key={`${event.source_url || event.start || event.date || index}-${index}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: Math.min(index * 0.04, 0.8) }}
            whileHover={{ y: -1 }}
            className="bg-black/40 border border-white/10 rounded-xl p-4 hover:border-emerald-500/20 transition-all">
            {(() => {
              const row = normalizeRow(event)
              return (
                <>
            <div className="flex items-center justify-between">
              <h3 className="text-white font-semibold">{row.title}</h3>
              <span className="text-xs px-2 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-md">{row.type}</span>
            </div>
            <p className="text-slate-400 text-sm mt-1">{row.date || 'Date not parsed'} • {row.collegeName}</p>
            {row.source && (
              <a href={row.source} target="_blank" rel="noreferrer" className="text-xs text-blue-400 hover:underline mt-2 inline-block">Source</a>
            )}
                </>
              )
            })()}
          </motion.div>
        ))}
        {!events.length && loading && (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {!events.length && !loading && <p className="text-slate-500 text-sm">No events loaded yet.</p>}
      </div>
    </div>
  )
}
