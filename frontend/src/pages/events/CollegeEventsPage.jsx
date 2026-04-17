import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  School, RefreshCw, ExternalLink, Search, CalendarDays,
  FileText, GraduationCap, AlertCircle, ChevronRight, X,
} from 'lucide-react'
import client from '../../api/client'
import toast from 'react-hot-toast'

// ── Constants ─────────────────────────────────────────────────────────────────
const CONFIG_KEY    = 'sais_college_config'       // { name, url }
const EVENTS_KEY    = 'sais_college_events_cache'  // { url, fetchedAt, events }

const TYPE_FILTERS = ['All', 'Notice', 'Exam', 'Event', 'Holiday', 'Lecture']

const TYPE_STYLE = {
  Notice:  { badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', icon: FileText },
  Exam:    { badge: 'bg-red-500/15 text-red-400 border-red-500/30',             icon: GraduationCap },
  Event:   { badge: 'bg-blue-500/15 text-blue-400 border-blue-500/30',          icon: CalendarDays },
  Holiday: { badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30',       icon: CalendarDays },
  Lecture: { badge: 'bg-purple-500/15 text-purple-400 border-purple-500/30',    icon: FileText },
}

function getTypeStyle(type = 'Notice') {
  return TYPE_STYLE[type] || TYPE_STYLE.Notice
}

function formatDate(raw) {
  if (!raw) return 'Date unknown'
  try {
    return new Date(raw).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return raw
  }
}

// ── Skeleton Card ─────────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="bg-black/40 border border-white/10 rounded-2xl p-5 animate-pulse">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="h-4 bg-slate-700/60 rounded w-16" />
        <div className="h-4 bg-slate-700/60 rounded w-4" />
      </div>
      <div className="h-5 bg-slate-700/60 rounded w-3/4 mb-2" />
      <div className="h-4 bg-slate-700/60 rounded w-1/2 mb-4" />
      <div className="h-4 bg-slate-700/60 rounded w-1/3" />
    </div>
  )
}

// ── Setup Card ────────────────────────────────────────────────────────────────
function SetupCard({ onSave }) {
  const [name, setName] = useState('')
  const [url, setUrl]   = useState('')
  const [err, setErr]   = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    if (!name.trim()) { setErr('Please enter your college name.'); return }
    const cleaned = url.trim().replace(/\/$/, '')
    try {
      const p = new URL(cleaned)
      if (!['http:', 'https:'].includes(p.protocol)) throw new Error()
    } catch {
      setErr('Please enter a valid URL starting with http:// or https://')
      return
    }
    onSave({ name: name.trim(), url: cleaned })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.45 }}
      className="max-w-lg mx-auto mt-12"
    >
      <div className="bg-black/50 border border-white/10 rounded-2xl p-8 backdrop-blur-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-emerald-500/15 rounded-xl flex items-center justify-center">
            <School size={20} className="text-emerald-400" />
          </div>
          <div>
            <h2 className="text-white font-bold text-lg">Set Up Your College</h2>
            <p className="text-slate-400 text-sm">One-time setup to fetch academic events.</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1.5">
              College Name
            </label>
            <input
              type="text"
              placeholder="e.g. Fr. Conceicao Rodrigues College"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full bg-black/40 text-slate-200 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/20 placeholder:text-slate-600 transition-all"
            />
          </div>

          <div>
            <label className="block text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1.5">
              College Website URL
            </label>
            <input
              type="url"
              placeholder="https://www.frcrce.ac.in"
              value={url}
              onChange={e => setUrl(e.target.value)}
              className="w-full bg-black/40 text-slate-200 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/20 placeholder:text-slate-600 transition-all"
            />
            <p className="text-slate-600 text-xs mt-1">The scraper will crawl this site for notices, exams, and events.</p>
          </div>

          {err && (
            <p className="flex items-center gap-1.5 text-red-400 text-xs">
              <AlertCircle size={13} /> {err}
            </p>
          )}

          <button
            type="submit"
            className="w-full mt-2 flex items-center justify-center gap-2 px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-xl text-sm transition-all"
          >
            Save &amp; Fetch Events <ChevronRight size={15} />
          </button>
        </form>
      </div>
    </motion.div>
  )
}

// ── Event Card ────────────────────────────────────────────────────────────────
function EventCard({ event, idx }) {
  const { badge, icon: Icon } = getTypeStyle(event.type)
  const primaryUrl = event.source_url   // notice/web page URL
  const pdfUrl     = event.pdf_url      // direct PDF (only present for PDF-sourced events)

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(idx * 0.03, 0.6) }}
      className="group bg-black/40 border border-white/10 rounded-2xl p-5 hover:border-emerald-500/30 hover:shadow-emerald-500/5 hover:shadow-lg transition-all backdrop-blur-sm flex flex-col gap-3"
    >
      {/* Type badge + top-right external link icon */}
      <div className="flex items-start justify-between gap-2">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${badge}`}>
          <Icon size={11} />
          {event.type}
        </span>
        {(primaryUrl || pdfUrl) && (
          <a
            href={primaryUrl || pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 text-slate-600 hover:text-emerald-400 transition-colors"
            title={primaryUrl ? "View notice page" : "Open PDF"}
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>

      {/* Title */}
      <p className="text-white font-semibold text-sm leading-snug line-clamp-3">
        {event.title}
      </p>

      {/* Meta */}
      <div className="mt-auto space-y-1">
        <p className="flex items-center gap-1.5 text-slate-500 text-xs">
          <CalendarDays size={11} className="text-emerald-500/60" />
          {formatDate(event.date)}
        </p>
        {event.college && (
          <p className="flex items-center gap-1.5 text-slate-600 text-xs truncate">
            <School size={11} />
            {event.college}
          </p>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-3 mt-1 flex-wrap">
        {/* View Source → notice web page */}
        {primaryUrl && (
          <a
            href={primaryUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-emerald-400/80 hover:text-emerald-400 transition-colors font-medium"
          >
            View Source <ExternalLink size={11} />
          </a>
        )}

        {/* Open PDF → direct PDF file (only when extracted from PDF) */}
        {pdfUrl && (
          <a
            href={pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-red-400/70 hover:text-red-400 transition-colors font-medium"
            title="Open source PDF"
          >
            Open PDF <ExternalLink size={11} />
          </a>
        )}
      </div>
    </motion.div>
  )
}


// ── Main Page ─────────────────────────────────────────────────────────────────
export default function CollegeEventsPage() {
  const [config, setConfig]           = useState(null)       // { name, url }
  const [events, setEvents]           = useState([])
  const [fetchedAt, setFetchedAt]     = useState(null)
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState(null)
  const [showSetup, setShowSetup]     = useState(false)

  const [search, setSearch]           = useState('')
  const [typeFilter, setTypeFilter]   = useState('All')
  const [sortOrder, setSortOrder]     = useState('latest')   // 'latest' | 'oldest'

  // ── Load config + cache from localStorage on mount ──────────────────────────
  useEffect(() => {
    try {
      // Remove old key from before the source_url fix (forces fresh data)
      localStorage.removeItem('sais_college_events_page_state')

      const raw = localStorage.getItem(CONFIG_KEY)
      if (!raw) return
      const cfg = JSON.parse(raw)
      if (cfg?.name && cfg?.url) {
        setConfig(cfg)
        // Load cached events — only accept v2+ cache (has pdf_url field)
        const cached = JSON.parse(localStorage.getItem(EVENTS_KEY) || 'null')
        const isV2 = cached?.version === 2
        if (isV2 && cached?.url === cfg.url && Array.isArray(cached.events) && cached.events.length > 0) {
          setEvents(cached.events)
          setFetchedAt(cached.fetchedAt)
        }
      }
    } catch {
      // ignore corrupt storage
    }
  }, [])


  // ── Auto-fetch when config is first set (no cached data) ────────────────────
  useEffect(() => {
    if (config && events.length === 0) {
      fetchEvents(config)
    }
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fetch ────────────────────────────────────────────────────────────────────
  async function fetchEvents(cfg) {
    if (!cfg?.url) return
    setLoading(true)
    setError(null)
    try {
      const { data } = await client.get('/college-events', {
        params: { college_url: cfg.url, college_name: cfg.name },
        timeout: 320000,
      })
      const now = Date.now()
      setEvents(data)
      setFetchedAt(now)
      localStorage.setItem(EVENTS_KEY, JSON.stringify({ version: 2, url: cfg.url, fetchedAt: now, events: data }))
      toast.success(`Fetched ${data.length} event${data.length !== 1 ? 's' : ''}`)
    } catch (err) {
      const msg = err.response?.data?.detail || `Could not fetch events from ${cfg.url}. Check the URL or try again.`
      setError(msg)
      toast.error('Fetch failed')
    } finally {
      setLoading(false)
    }
  }

  // ── Handle setup save ────────────────────────────────────────────────────────
  function handleSave(newConfig) {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(newConfig))
    setConfig(newConfig)
    setEvents([])
    setShowSetup(false)
    fetchEvents(newConfig)
  }

  // ── Filtered + sorted events (frontend only) ─────────────────────────────────
  const filtered = useMemo(() => {
    let result = [...events]
    if (typeFilter !== 'All') {
      result = result.filter(e => (e.type || 'Notice') === typeFilter)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(e => (e.title || '').toLowerCase().includes(q))
    }
    result.sort((a, b) => {
      const da = a.date || ''
      const db = b.date || ''
      return sortOrder === 'latest' ? db.localeCompare(da) : da.localeCompare(db)
    })
    return result
  }, [events, typeFilter, search, sortOrder])

  const lastFetchedLabel = useMemo(() => {
    if (!fetchedAt) return null
    return new Date(fetchedAt).toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  }, [fetchedAt])

  // ── Show setup if no config ───────────────────────────────────────────────────
  if (!config && !showSetup) {
    return (
      <div className="p-4 md:p-8 max-w-6xl mx-auto">
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
          <h1 className="font-display text-3xl text-white mb-1">College Academic Events</h1>
          <p className="text-slate-400 text-sm mb-8">Notices, exams, and academic calendar from your college.</p>
        </motion.div>
        <SetupCard onSave={handleSave} />
      </div>
    )
  }

  if (showSetup) {
    return (
      <div className="p-4 md:p-8 max-w-6xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => setShowSetup(false)}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
          <h1 className="font-display text-2xl text-white">Change College</h1>
        </div>
        <SetupCard onSave={handleSave} />
      </div>
    )
  }

  // ── Main Layout ───────────────────────────────────────────────────────────────
  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-2"
      >
        <div>
          <h1 className="font-display text-3xl text-white mb-1">College Academic Events</h1>
          <p className="text-slate-400 text-sm">Notices, exams, and academic calendar from your college.</p>
        </div>

        <button
          onClick={() => fetchEvents(config)}
          disabled={loading}
          className="flex-shrink-0 flex items-center gap-2 px-4 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-bold rounded-xl text-sm transition-all"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Fetching…' : 'Fetch Latest Events'}
        </button>
      </motion.div>

      {/* ── College info bar ─────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="flex flex-wrap items-center gap-3 mb-1"
      >
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5">
          <School size={13} className="text-emerald-400" />
          <span className="text-slate-200 text-xs font-semibold">{config.name}</span>
        </div>
        <span className="text-slate-500 text-xs">{new URL(config.url).hostname}</span>
        <button
          onClick={() => setShowSetup(true)}
          className="text-xs text-emerald-400/70 hover:text-emerald-400 underline underline-offset-2 transition-colors"
        >
          Change College
        </button>
      </motion.div>

      {lastFetchedLabel && (
        <p className="text-slate-600 text-xs mb-5">Last fetched: {lastFetchedLabel}</p>
      )}

      {/* ── Error banner ─────────────────────────────────────────────── */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-5 flex items-start gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
          >
            <AlertCircle size={16} className="text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-red-300 text-sm font-medium">Fetch failed</p>
              <p className="text-red-400/70 text-xs mt-0.5">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="text-red-400/50 hover:text-red-400">
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Filter bar ───────────────────────────────────────────────── */}
      {(events.length > 0 || loading) && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="flex flex-col gap-3 mb-5"
        >
          {/* Top row: search + sort */}
          <div className="flex flex-col sm:flex-row gap-2">
            {/* Search */}
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="Search events…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full bg-black/40 text-slate-300 border border-white/10 rounded-xl pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-emerald-500/50 placeholder:text-slate-600 transition-all"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Sort */}
            <div className="relative flex-shrink-0">
              <select
                value={sortOrder}
                onChange={e => setSortOrder(e.target.value)}
                className="bg-black/40 text-slate-300 border border-white/10 rounded-xl pl-3 pr-8 py-2 text-sm focus:outline-none focus:border-emerald-500/50 appearance-none transition-all cursor-pointer"
              >
                <option value="latest">Latest First</option>
                <option value="oldest">Oldest First</option>
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-slate-500">
                <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20">
                  <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
                </svg>
              </div>
            </div>
          </div>

          {/* Type filter pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
            {TYPE_FILTERS.map(t => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border ${
                  typeFilter === t
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : 'bg-black/30 text-slate-400 border-white/5 hover:text-white hover:bg-white/10'
                }`}
              >
                {t}
              </button>
            ))}

            {/* Result count */}
            <span className="ml-auto text-slate-500 text-xs whitespace-nowrap pl-2 flex-shrink-0">
              Showing <span className="text-emerald-400 font-semibold">{filtered.length}</span>{' '}
              {filtered.length !== events.length && `of ${events.length} `}event{filtered.length !== 1 ? 's' : ''}
            </span>
          </div>
        </motion.div>
      )}

      {/* ── Card grid ────────────────────────────────────────────────── */}
      {loading && events.length === 0 ? (
        // Skeleton state
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : events.length === 0 && !loading ? (
        // Empty: never fetched
        <div className="flex flex-col items-center justify-center py-24 text-center bg-black/20 rounded-2xl border border-white/5">
          <School size={52} className="text-slate-700 mb-4" />
          <p className="text-slate-400 font-medium mb-1">No events yet</p>
          <p className="text-slate-600 text-sm mb-4">Click <strong className="text-slate-400">Fetch Latest Events</strong> to scrape your college site.</p>
          <button
            onClick={() => fetchEvents(config)}
            className="px-4 py-2 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-400 text-sm rounded-xl transition-all"
          >
            Fetch Now
          </button>
        </div>
      ) : filtered.length === 0 ? (
        // Filtered empty
        <div className="flex flex-col items-center justify-center py-20 text-center bg-black/20 rounded-2xl border border-white/5">
          <Search size={40} className="text-slate-700 mb-3" />
          <p className="text-slate-400 font-medium mb-1">No events match your filters</p>
          <button
            onClick={() => { setSearch(''); setTypeFilter('All') }}
            className="mt-3 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition-colors"
          >
            Clear Filters
          </button>
        </div>
      ) : (
        <motion.div
          layout
          className="grid grid-cols-1 sm:grid-cols-2 gap-4"
        >
          <AnimatePresence mode="popLayout">
            {filtered.map((event, idx) => (
              <EventCard
                key={`${event.source_url || event.date || idx}-${event.title?.slice(0, 20)}-${idx}`}
                event={event}
                idx={idx}
              />
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Loading overlay on re-fetch */}
      {loading && events.length > 0 && (
        <div className="flex items-center justify-center gap-2 mt-6 text-slate-400 text-sm">
          <RefreshCw size={14} className="animate-spin text-emerald-400" />
          Refreshing events from {config.name}…
        </div>
      )}
    </div>
  )
}
