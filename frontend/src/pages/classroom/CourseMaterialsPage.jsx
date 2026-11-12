import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useLocation } from 'react-router-dom'
import {
  FileText, Link as LinkIcon, Youtube, Calendar,
  RefreshCw, ExternalLink, BookOpen, FileQuestion, Search
} from 'lucide-react'
import client from '../../api/client'
import toast from 'react-hot-toast'

const CLASSROOM_MATERIALS_KEY = 'sais_classroom_materials'
const CLASSROOM_LAST_SYNC_KEY = 'sais_classroom_last_sync'

const TABS = [
  { id: 'all', label: 'All' },
  { id: 'drive', label: 'Files' },
  { id: 'link', label: 'Links' },
  { id: 'youtube', label: 'YouTube' },
  { id: 'form', label: 'Forms' }
]

function MaterialIcon({ type }) {
  switch (type) {
    case 'drive':  return <FileText     size={18} className="text-emerald-400 flex-shrink-0" />
    case 'youtube':return <Youtube      size={18} className="text-emerald-400 flex-shrink-0" />
    case 'link':   return <LinkIcon     size={18} className="text-emerald-400 flex-shrink-0" />
    case 'form':   return <FileQuestion size={18} className="text-emerald-400 flex-shrink-0" />
    default:       return <FileText     size={18} className="text-emerald-400 flex-shrink-0" />
  }
}

function AttachmentChip({ att }) {
  const icons = { drive: '📄', youtube: '▶️', link: '🔗', form: '📝' }
  return (
    <a
      href={att.url}
      target="_blank"
      rel="noopener noreferrer"
      title={att.title}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-slate-700/60 text-emerald-400 text-xs rounded-lg hover:bg-slate-600/80 transition-colors"
    >
      <span>{icons[att.type] ?? '📎'}</span>
      <span className="max-w-[180px] truncate">{att.title}</span>
    </a>
  )
}

export default function CourseMaterialsPage() {
  const [materials, setMaterials]     = useState([])
  const [lastSyncedAt, setLastSyncedAt] = useState(null)
  const [loading, setLoading]         = useState(false)
  const [authError, setAuthError]     = useState(null) // 'not_connected' | 'expired' | null
  
  const [filterCourse, setFilterCourse] = useState('All Courses')
  const [filterType, setFilterType] = useState('all')
  const [sortOption, setSortOption] = useState('latest')
  const [searchQuery, setSearchQuery] = useState('')
  const location = useLocation()

  // --- Load from localStorage on mount ---
  useEffect(() => {
    try {
      const cached = localStorage.getItem(CLASSROOM_MATERIALS_KEY)
      if (cached) setMaterials(JSON.parse(cached))
      const ts = Number(localStorage.getItem(CLASSROOM_LAST_SYNC_KEY))
      if (Number.isFinite(ts) && ts > 0) setLastSyncedAt(ts)
    } catch {
      // stale or corrupt cache — ignore
    }
  }, [])

  // --- Detect "?connected=1" redirect from OAuth ---
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('connected') === '1') toast.success('Google Classroom connected')
  }, [location.search])

  function connectGoogle() {
    try {
      const apiBase = client.defaults.baseURL || '/api/v1'
      const origin = apiBase.startsWith('http') ? new URL(apiBase).origin : window.location.origin
      window.location.href = `${origin}/auth/google/connect`
    } catch {
      toast.error('Failed to start Google OAuth')
    }
  }

  const syncMaterials = useCallback(async () => {
    setLoading(true)
    try {
      // Check connection before making sync request
      const statusResp = await client.get('/classroom/status')
      if (!statusResp.data?.connected) { setAuthError('not_connected'); return }

      // Use combined sync (fetches courses once, returns events + materials)
      const { data } = await client.get('/classroom/sync', { timeout: 300000 })
      const next = data?.materials ?? []
      const syncedAt = Date.now()

      setMaterials(next)
      setLastSyncedAt(syncedAt)
      setAuthError(null)
      localStorage.setItem(CLASSROOM_MATERIALS_KEY, JSON.stringify(next))
      localStorage.setItem(CLASSROOM_LAST_SYNC_KEY, String(syncedAt))
      toast.success(`${next.length} material${next.length !== 1 ? 's' : ''} synced`)
    } catch (error) {
      const status = error.response?.status
      const detail = (error.response?.data?.detail || '').toLowerCase()
      if (status === 404 || detail.includes('not connected')) {
        setAuthError('not_connected')
      } else if (status === 401 || status === 403 || detail.includes('expired') || detail.includes('revoked')) {
        setAuthError('expired')
      } else {
        toast.error(error.response?.data?.detail || 'Sync failed')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const lastSyncedLabel = useMemo(() => {
    if (!lastSyncedAt) return 'Not synced yet'
    return new Date(lastSyncedAt).toLocaleString()
  }, [lastSyncedAt])

  const distinctCourses = useMemo(() => {
    const courses = new Set(materials.map(m => m.course).filter(Boolean))
    return ['All Courses', ...Array.from(courses).sort()]
  }, [materials])

  const filteredAndSortedMaterials = useMemo(() => {
    let result = [...materials]

    if (filterCourse !== 'All Courses') {
      result = result.filter(m => (m.course || '') === filterCourse)
    }

    if (filterType !== 'all') {
      result = result.filter(m => {
        const types = [
          m.material_type,
          m.source,
          ...(m.attachments || []).map(a => a.type)
        ].filter(Boolean).map(t => t.toLowerCase())
        
        if (filterType === 'drive') return types.some(t => t.includes('drive') || t.includes('file') || t.includes('assignment'))
        if (filterType === 'youtube') return types.some(t => t.includes('youtube') || t.includes('video'))
        if (filterType === 'link') return types.some(t => t.includes('link') || t.includes('url'))
        if (filterType === 'form') return types.some(t => t.includes('form'))
        return false
      })
    }

    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase()
      result = result.filter(m => 
        (m.title && m.title.toLowerCase().includes(q)) ||
        (m.description && m.description.toLowerCase().includes(q))
      )
    }

    result.sort((a, b) => {
      if (sortOption === 'latest' || sortOption === 'oldest') {
        const timeA = new Date(a.creation_time || a.update_time || a.posted_at || a.due_date || 0).getTime()
        const timeB = new Date(b.creation_time || b.update_time || b.posted_at || b.due_date || 0).getTime()
        const diff = sortOption === 'latest' ? timeB - timeA : timeA - timeB
        if (diff !== 0) return diff
      }
      
      if (sortOption === 'az' || sortOption === 'za') {
        const titleA = (a.title || '').toLowerCase()
        const titleB = (b.title || '').toLowerCase()
        const cmp = sortOption === 'az' ? titleA.localeCompare(titleB) : titleB.localeCompare(titleA)
        if (cmp !== 0) return cmp
      }
      
      return 0
    })

    return result
  }, [materials, filterCourse, filterType, searchQuery, sortOption])

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      {/* ── Header ─────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-start justify-between gap-4 flex-wrap mb-6"
      >
        <div>
          <div className="flex items-center gap-2 mb-1">
            <BookOpen size={22} className="text-emerald-400" />
            <h1 className="font-display text-3xl text-white">Course Materials</h1>
          </div>
          <p className="text-slate-400 text-sm">
            Documents, files, and resources posted by your teachers in Google Classroom.
          </p>
        </div>

        <button
          onClick={syncMaterials}
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold rounded-xl text-sm transition-all flex-shrink-0"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Syncing…' : 'Sync Materials'}
        </button>
      </motion.div>

      <p className="text-slate-500 text-xs mb-6">Last synced: {lastSyncedLabel}</p>

      {/* ── Auth error banner ───────────────────────────────── */}
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
                : 'Connect your Google account to sync course materials.'}
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

      {/* ── Filters ─────────────────────────────────────────── */}
      {materials.length > 0 && (
        <motion.div 
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex flex-col gap-4 mb-6"
        >
          {/* Top row: Search, Course, Sort */}
          <div className="flex flex-col sm:flex-row gap-3">
             <div className="relative flex-1 min-w-[200px]">
               <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
               <input
                 type="text"
                 placeholder="Search materials..."
                 value={searchQuery}
                 onChange={e => setSearchQuery(e.target.value)}
                 className="w-full bg-black/40 text-slate-300 border border-white/10 rounded-xl pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-emerald-500/50 placeholder:text-slate-500 transition-colors"
               />
             </div>
             
             <div className="flex flex-col sm:flex-row gap-3">
               <div className="relative flex-1 sm:flex-initial">
                 <select
                   value={filterCourse}
                   onChange={e => setFilterCourse(e.target.value)}
                   className="w-full bg-black/40 text-slate-300 border border-white/10 rounded-xl pl-3 pr-8 py-2 text-sm focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 appearance-none min-w-[160px] sm:max-w-[200px] truncate"
                 >
                   {distinctCourses.map(course => (
                     <option key={course} value={course}>{course}</option>
                   ))}
                 </select>
                 <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400">
                   <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" fillRule="evenodd"></path></svg>
                 </div>
               </div>

               <div className="relative flex-1 sm:flex-initial">
                 <select
                   value={sortOption}
                   onChange={e => setSortOption(e.target.value)}
                   className="w-full bg-black/40 text-slate-300 border border-white/10 rounded-xl pl-3 pr-8 py-2 text-sm focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 appearance-none min-w-[140px]"
                 >
                   <option value="latest">Latest First</option>
                   <option value="oldest">Oldest First</option>
                   <option value="az">A–Z Title</option>
                   <option value="za">Z–A Title</option>
                 </select>
                 <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400">
                   <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" fillRule="evenodd"></path></svg>
                 </div>
               </div>
             </div>
          </div>
          
          {/* Bottom row: Type tabs & Results count */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 mt-1">
            <div className="flex items-center gap-2 overflow-x-auto pb-2 sm:pb-0 w-full sm:w-auto" style={{ scrollbarWidth: 'none' }}>
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setFilterType(tab.id)}
                  className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all ${
                    filterType === tab.id 
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' 
                      : 'bg-black/40 text-slate-400 border border-white/5 hover:text-white hover:bg-white/10'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="text-slate-500 text-sm whitespace-nowrap">
              Showing <span className="text-emerald-400 font-medium">{filteredAndSortedMaterials.length}</span> of {materials.length} materials
            </div>
          </div>
        </motion.div>
      )}

      {/* ── Materials list ──────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.1 }}
      >
        {materials.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <BookOpen size={52} className="text-slate-700 mb-4" />
            <p className="text-slate-400 font-medium mb-1">No materials yet</p>
            <p className="text-slate-600 text-sm">
              Click <strong className="text-slate-400">Sync Materials</strong> to import from Google Classroom.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredAndSortedMaterials.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center bg-black/20 rounded-2xl border border-white/5">
                <Search size={40} className="text-slate-600 mb-3" />
                <p className="text-slate-400 font-medium">No materials found for the selected filters</p>
                <button 
                  onClick={() => {
                    setFilterCourse('All Courses')
                    setFilterType('all')
                    setSearchQuery('')
                    setSortOption('latest')
                  }}
                  className="mt-4 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition-colors"
                >
                  Clear Filters
                </button>
              </div>
            ) : (
              filteredAndSortedMaterials.map((mat, idx) => {
                const openUrl = mat.alternate_link || mat.attachments?.[0]?.url
              return (
                <motion.div
                  key={`${mat.id || 'mat'}-${idx}-${mat.course}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.025 }}
                  className="bg-black/40 border border-white/10 rounded-2xl p-5 hover:border-emerald-500/30 transition-all backdrop-blur-sm"
                >
                  <div className="flex items-start justify-between gap-4">
                    {/* Left: info */}
                    <div className="min-w-0 flex-1">
                      {/* Title row */}
                      <div className="flex items-center gap-2.5 mb-2">
                        <MaterialIcon type={mat.material_type || (mat.attachments?.[0]?.type)} />
                        <p className="text-white font-semibold text-sm leading-snug">
                          {mat.title}
                        </p>
                      </div>

                      {/* Meta: course + date */}
                      <div className="flex items-center flex-wrap gap-2 mb-2.5">
                        <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-full text-xs font-medium">
                          {mat.course}
                        </span>
                        {mat.creation_time && (
                          <span className="flex items-center gap-1 text-slate-500 text-xs">
                            <Calendar size={11} />
                            Posted: {new Date(mat.creation_time).toLocaleDateString()}
                          </span>
                        )}
                        {mat.source && mat.source !== 'courseWorkMaterial' && (
                          <span className="px-2 py-0.5 bg-slate-700/60 text-slate-400 rounded-full text-xs">
                            {mat.source}
                          </span>
                        )}
                      </div>

                      {/* Description */}
                      {mat.description && (
                        <p className="text-slate-500 text-xs line-clamp-2 mb-2.5">
                          {mat.description}
                        </p>
                      )}

                      {/* Attachment chips */}
                      {mat.attachments && mat.attachments.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-1">
                          {mat.attachments.map((att, ai) => (
                            <AttachmentChip key={ai} att={att} />
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Right: Open button */}
                    {openUrl && (
                      <a
                        href={openUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 bg-emerald-400/10 hover:bg-emerald-400/20 border border-emerald-400/30 text-emerald-400 text-xs font-semibold rounded-xl transition-all"
                      >
                        Open
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                </motion.div>
              )
            })
            )}
          </div>
        )}
      </motion.div>
    </div>
  )
}
