import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useLocation } from 'react-router-dom'
import {
  FileText, Link as LinkIcon, Youtube, Calendar,
  RefreshCw, ExternalLink, BookOpen, FileQuestion,
} from 'lucide-react'
import client from '../../api/client'
import toast from 'react-hot-toast'

const CLASSROOM_MATERIALS_KEY = 'sais_classroom_materials'
const CLASSROOM_LAST_SYNC_KEY = 'sais_classroom_last_sync'

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
      const token = localStorage.getItem('sais_token')
      if (!token) { toast.error('Please login first'); return }
      const apiBase   = (client.defaults.baseURL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
      const apiOrigin = new URL(apiBase).origin
      window.location.href = `${apiOrigin}/auth/google/connect?token=${encodeURIComponent(token)}`
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

  return (
    <div className="p-8 max-w-5xl mx-auto">
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
            {materials.map((mat, idx) => {
              const openUrl = mat.alternate_link || mat.attachments?.[0]?.url
              return (
                <motion.div
                  key={mat.id || idx}
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
            })}
          </div>
        )}
      </motion.div>
    </div>
  )
}
