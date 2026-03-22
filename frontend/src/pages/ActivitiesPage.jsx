import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getActivities, createActivity, deleteActivityById, refreshConflicts } from '../api/activities'
import { format } from 'date-fns'
import { Plus, AlertTriangle, X, Trophy, RefreshCw, Trash2, Repeat } from 'lucide-react'
import toast from 'react-hot-toast'

const CATEGORIES = ['Sports', 'Cultural', 'Tech Club', 'Volunteer', 'Art', 'Music', 'Other']

const RECURRENCE_OPTIONS = [
  { value: 'none',         label: 'Does not repeat' },
  { value: 'daily',        label: 'Daily' },
  { value: 'every_2_days', label: 'Every 2 days' },
  { value: 'every_3_days', label: 'Every 3 days' },
  { value: 'weekly',       label: 'Weekly' },
  { value: 'biweekly',     label: 'Every 2 weeks' },
  { value: 'monthly',      label: 'Monthly' },
  { value: 'custom',       label: 'Custom…' },
]

function ActivityModal({ onClose, onSave }) {
  const [form, setForm] = useState({
    title: '', category: '', activity_date: '',
    start_time: '', end_time: '', location: '', description: '',
    recurrence_type: 'none',
    recurrence_start_date: '', recurrence_end_date: '',
    custom_interval: 1, custom_interval_unit: 'days',
  })
  const [saving, setSaving] = useState(false)

  const isRecurring = form.recurrence_type !== 'none'

  async function submit(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      )
      if (isRecurring) {
        payload.activity_date = null
        payload.custom_interval = form.custom_interval ? Number(form.custom_interval) : null
      }
      await onSave(payload)
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create activity')
    } finally {
      setSaving(false)
    }
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
        className="bg-black/80 border border-white/10 rounded-2xl w-full max-w-lg backdrop-blur-md max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="font-display text-xl text-white">Add Activity</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300"><X size={20} /></button>
        </div>

        <form onSubmit={submit} className="p-6 space-y-4">
          {/* Title */}
          <div>
            <label className={lbl}>Title *</label>
            <input className={inp} required value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="Activity name" />
          </div>

          {/* Category & Date */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={lbl}>Category</label>
              <select className={inp} value={form.category}
                onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                <option value="">Select…</option>
                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            {!isRecurring && (
              <div>
                <label className={lbl}>Date *</label>
                <input className={inp} type="date" required={!isRecurring}
                  value={form.activity_date}
                  onChange={e => setForm(f => ({ ...f, activity_date: e.target.value }))} />
              </div>
            )}
          </div>

          {/* Times */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={lbl}>Start Time</label>
              <input className={inp} type="time" value={form.start_time}
                onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
            </div>
            <div>
              <label className={lbl}>End Time</label>
              <input className={inp} type="time" value={form.end_time}
                onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
            </div>
          </div>

          {/* ── Recurrence ─────────────────────────────────── */}
          <div className="pt-3 border-t border-white/10 space-y-3">
            <div>
              <label className={lbl}>Recurrence</label>
              <select className={inp} value={form.recurrence_type}
                onChange={e => setForm(f => ({ ...f, recurrence_type: e.target.value }))}>
                {RECURRENCE_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            <AnimatePresence>
              {isRecurring && (
                <motion.div
                  key="date-range"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-emerald-400 mb-1.5 uppercase tracking-wider">
                          Start Date *
                        </label>
                        <input className={inp} type="date" required={isRecurring}
                          value={form.recurrence_start_date}
                          onChange={e => setForm(f => ({ ...f, recurrence_start_date: e.target.value }))} />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-emerald-400 mb-1.5 uppercase tracking-wider">
                          End Date *
                        </label>
                        <input className={inp} type="date" required={isRecurring}
                          min={form.recurrence_start_date}
                          value={form.recurrence_end_date}
                          onChange={e => setForm(f => ({ ...f, recurrence_end_date: e.target.value }))} />
                      </div>
                    </div>

                    {form.recurrence_type === 'custom' && (
                      <div>
                        <label className="block text-xs font-medium text-emerald-400 mb-1.5 uppercase tracking-wider">
                          Repeat Every
                        </label>
                        <div className="flex items-center gap-2">
                          <input className={`${inp} w-24`} type="number" min="1" max="365"
                            value={form.custom_interval}
                            onChange={e => setForm(f => ({ ...f, custom_interval: e.target.value }))} />
                          <select className={`${inp} flex-1`} value={form.custom_interval_unit}
                            onChange={e => setForm(f => ({ ...f, custom_interval_unit: e.target.value }))}>
                            <option value="days">Days</option>
                            <option value="weeks">Weeks</option>
                            <option value="months">Months</option>
                          </select>
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Location & Notes */}
          <div>
            <label className={lbl}>Location</label>
            <input className={inp} value={form.location}
              onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
              placeholder="Venue / Room" />
          </div>
          <div>
            <label className={lbl}>Notes</label>
            <textarea className={`${inp} resize-none`} rows={2}
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 border border-white/10 rounded-xl text-sm text-gray-400 hover:text-gray-200">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 bg-emerald-500 text-black font-semibold rounded-xl text-sm hover:bg-emerald-600 disabled:opacity-50">
              {saving ? 'Saving…' : isRecurring ? 'Create Recurring' : 'Add Activity'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}

/** Inline delete dialog shown on the card itself for recurring activities */
function DeleteDialog({ onCancel, onDelete }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="absolute inset-0 bg-black/90 backdrop-blur-sm rounded-2xl flex flex-col items-center justify-center gap-3 p-4 z-10"
    >
      <p className="text-xs text-center text-gray-300 font-medium">Delete this recurring activity?</p>
      <div className="flex flex-col gap-2 w-full">
        <button
          onClick={() => onDelete(false)}
          className="w-full py-2 text-xs bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-300 rounded-lg transition-all">
          This occurrence only
        </button>
        <button
          onClick={() => onDelete(true)}
          className="w-full py-2 text-xs bg-red-600/30 hover:bg-red-600/40 border border-red-600/40 text-red-200 rounded-lg transition-all">
          Entire series
        </button>
        <button onClick={onCancel}
          className="w-full py-2 text-xs text-gray-500 hover:text-gray-300 transition-all">
          Cancel
        </button>
      </div>
    </motion.div>
  )
}

export default function ActivitiesPage() {
  const [activities, setActivities] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)

  async function load() {
    try { const { data } = await getActivities(); setActivities(data) }
    catch { } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function handleCreate(form) {
    await createActivity(form)
    load()
    toast.success(form.recurrence_type === 'none' ? 'Activity added!' : 'Recurring activities created!')
  }

  async function handleDelete(activity, deleteSeries) {
    setDeletingId(null)
    try {
      await deleteActivityById(activity.id, deleteSeries)
      load()
      toast.success(deleteSeries ? 'Entire series deleted' : 'Activity deleted')
    } catch {
      toast.error('Failed to delete')
    }
  }

  function requestDelete(activity) {
    if (activity.is_recurring_instance) {
      setDeletingId(activity.id)
    } else {
      if (!confirm('Delete activity?')) return
      handleDelete(activity, false)
    }
  }

  async function handleRefresh() {
    setRefreshing(true)
    try { const { data } = await refreshConflicts(); toast.success(`Updated ${data.updated} conflicts`) }
    catch { toast.error('Failed') }
    finally { setRefreshing(false); load() }
  }

  const conflicts = activities.filter(a => a.has_conflict)

  return (
    <div className="p-8">
      {loading ? (
        <div className="space-y-4 animate-fade-in">
          <div className="skeleton h-8 w-40 mb-2" />
          <div className="skeleton h-4 w-28 mb-6" />
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <>
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="flex items-center justify-between mb-8"
          >
            <div>
              <h1 className="font-display text-3xl text-white">Activities</h1>
              <p className="text-slate-400 text-sm mt-1">
                {activities.length} activities · {conflicts.length} conflict{conflicts.length !== 1 ? 's' : ''}
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={handleRefresh} disabled={refreshing}
                className="flex items-center gap-2 px-3 py-2.5 border border-white/10 rounded-xl text-sm text-gray-400 hover:text-emerald-400 hover:border-emerald-500/30 transition-all">
                <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Check Conflicts
              </button>
              <motion.button
                whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                onClick={() => setShowModal(true)}
                className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500 text-black font-semibold rounded-xl hover:bg-emerald-600 transition-colors text-sm"
              >
                <Plus size={16} /> Add Activity
              </motion.button>
            </div>
          </motion.div>

          {conflicts.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="bg-red-400/10 border border-red-400/20 rounded-xl p-4 mb-6 flex items-start gap-3"
            >
              <AlertTriangle size={16} className="text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-400">Schedule Conflicts Detected</p>
                <p className="text-xs text-red-400/70 mt-0.5">
                  {conflicts.length} activit{conflicts.length !== 1 ? 'ies clash' : 'y clashes'} with assignment deadlines.
                </p>
              </div>
            </motion.div>
          )}

          {activities.length === 0
            ? <div className="py-20 text-center bg-white/[0.02] border border-white/10 rounded-2xl">
                <Trophy size={36} className="text-slate-600 mx-auto mb-3" />
                <p className="text-slate-400 font-medium">No activities yet</p>
                <p className="text-slate-500 text-sm mt-1">Add clubs, sports, or events to track them</p>
              </div>
            : <div className="grid grid-cols-3 gap-4">
                {activities.map((a, i) => (
                  <motion.div
                    key={a.id}
                    initial={{ opacity: 0, y: 12, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.4, delay: i * 0.04 }}
                    whileHover={{ y: -2 }}
                    className={`relative bg-white/[0.02] border rounded-2xl p-5 hover:border-emerald-500/20 transition-all ${a.has_conflict ? 'border-red-400/30' : 'border-white/10'}`}
                  >
                    {/* Inline delete dialog for recurring activities */}
                    <AnimatePresence>
                      {deletingId === a.id && (
                        <DeleteDialog
                          onCancel={() => setDeletingId(null)}
                          onDelete={(series) => handleDelete(a, series)}
                        />
                      )}
                    </AnimatePresence>

                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-medium text-white truncate">{a.title}</h3>
                          {a.is_recurring_instance && (
                            <span className="flex items-center gap-1 text-[10px] text-emerald-400/80 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded-full flex-shrink-0">
                              <Repeat size={9} /> Recurring
                            </span>
                          )}
                        </div>
                        {a.category && <span className="text-xs text-blue-400 font-medium mt-0.5 block">{a.category}</span>}
                      </div>
                      <button
                        onClick={() => requestDelete(a)}
                        className="text-slate-600 hover:text-red-400 transition-all ml-2 flex-shrink-0">
                        <Trash2 size={14} />
                      </button>
                    </div>

                    <div className="space-y-1 text-xs text-slate-400 mb-3">
                      <p>📅 {a.activity_date ? format(new Date(a.activity_date + 'T00:00:00'), 'EEEE, MMM d, yyyy') : 'No date'}</p>
                      {(a.start_time || a.end_time) && <p>🕐 {a.start_time || ''}{a.start_time && a.end_time ? ' – ' : ''}{a.end_time || ''}</p>}
                      {a.location && <p>📍 {a.location}</p>}
                    </div>

                    {a.has_conflict && (
                      <div className="bg-red-400/10 rounded-lg p-2.5 mt-2">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <AlertTriangle size={11} className="text-red-400" />
                          <span className="text-xs text-red-400 font-medium">Deadline Conflict</span>
                        </div>
                        <p className="text-xs text-red-400/70">{a.conflict_detail}</p>
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
          }
          {showModal && <ActivityModal onClose={() => setShowModal(false)} onSave={handleCreate} />}
        </>
      )}
    </div>
  )
}
