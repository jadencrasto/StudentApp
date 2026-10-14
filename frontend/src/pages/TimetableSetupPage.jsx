import { useEffect, useMemo, useState } from 'react'
import { Grid3X3, List, Save, Upload, Calendar, CheckCircle2, Info, User, Clock } from 'lucide-react'
import toast from 'react-hot-toast'

import TimetableGridView from '../components/timetable/TimetableGridView'
import TimetableListEditor from '../components/timetable/TimetableListEditor'
import UploadTimetable from '../components/timetable/UploadTimetable'
import { getSubjects } from '../api/attendance'
import { bulkSaveTimetableEntries, getTimetableEntries } from '../api/timetable'
import { classTimetableAPI } from '../api/client'

const DAYS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
]

export default function TimetableSetupPage() {
  const [activeTab, setActiveTab] = useState('class') // 'class' | 'personal'
  const [view, setView] = useState('grid')
  const [entries, setEntries] = useState([])
  const [subjects, setSubjects] = useState([])
  const [showUpload, setShowUpload] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  // Official class timetable state
  const [classTimetable, setClassTimetable] = useState({
    enrolled: false,
    cohort_id: null,
    cohort_name: null,
    has_timetable: false,
    published_at: null,
    entries: [],
  })

  useEffect(() => {
    async function loadData() {
      try {
        const [
          { data: timetable },
          { data: subjectList },
          classRes,
        ] = await Promise.all([
          getTimetableEntries(),
          getSubjects(),
          classTimetableAPI.getStudentClassTimetable().catch(() => ({ data: null })),
        ])
        setEntries(timetable)
        setSubjects(subjectList)

        if (classRes?.data) {
          setClassTimetable(classRes.data)
          // Default to class timetable tab if student has an official published timetable
          if (classRes.data.has_timetable) {
            setActiveTab('class')
          } else {
            setActiveTab('personal')
          }
        } else {
          setActiveTab('personal')
        }
      } catch {
        toast.error('Failed to load timetable data')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [])

  const savePayload = useMemo(
    () => entries.map((entry) => ({
      subject_id: entry.subject_id,
      day_of_week: Number(entry.day_of_week),
      start_time: entry.start_time,
      end_time: entry.end_time,
      room: entry.room || null,
      notes: entry.notes || null,
    })),
    [entries]
  )

  async function handleSave() {
    setSaving(true)
    try {
      await bulkSaveTimetableEntries(savePayload)
      toast.success('Personal timetable saved successfully')
      const { data: refreshed } = await getTimetableEntries()
      setEntries(refreshed)
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save timetable')
    } finally {
      setSaving(false)
    }
  }

  // Group class timetable entries by day of week
  const classEntriesByDay = useMemo(() => {
    const map = {}
    DAYS.forEach((d) => {
      map[d.value] = []
    })
    ;(classTimetable.entries || []).forEach((e) => {
      const day = Number(e.day_of_week)
      if (map[day] !== undefined) {
        map[day].push(e)
      }
    })
    // Sort each day by start_time
    Object.keys(map).forEach((k) => {
      map[k].sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''))
    })
    return map
  }, [classTimetable.entries])

  return (
    <div className="p-6 lg:p-8">
      {loading ? (
        <div className="flex items-center justify-center py-32">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Top Header */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div>
              <h1 className="font-display text-3xl text-white mb-1">Timetable Schedule</h1>
              <p className="text-slate-400 text-sm">
                View your official class schedule and manage your personal routine
              </p>
            </div>

            {/* Switcher: Official Class vs Personal */}
            {classTimetable.enrolled && (
              <div className="flex items-center gap-1 bg-black/50 border border-emerald-500/30 rounded-xl p-1">
                <button
                  onClick={() => setActiveTab('class')}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                    activeTab === 'class'
                      ? 'bg-emerald-500 text-black shadow-lg shadow-emerald-500/20'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Calendar size={14} /> Official Class Timetable
                  {classTimetable.has_timetable && (
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  )}
                </button>

                <button
                  onClick={() => setActiveTab('personal')}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                    activeTab === 'personal'
                      ? 'bg-emerald-500 text-black shadow-lg shadow-emerald-500/20'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <User size={14} /> Personal Schedule
                </button>
              </div>
            )}
          </div>

          {/* ─────────────────────────────────────────────────────────────
              VIEW 1: OFFICIAL CLASS TIMETABLE (Read-Only)
          ───────────────────────────────────────────────────────────── */}
          {activeTab === 'class' && classTimetable.enrolled && (
            <div className="space-y-6">
              {/* Class Info Banner */}
              <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-black border border-emerald-500/30 backdrop-blur-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                      <CheckCircle2 size={11} /> Official Class Schedule
                    </span>
                    <span className="text-xs text-slate-400">Read-Only</span>
                  </div>
                  <h2 className="text-xl font-bold text-white tracking-tight">
                    {classTimetable.cohort_name}
                  </h2>
                  {classTimetable.has_timetable && classTimetable.published_at && (
                    <p className="text-xs text-slate-400 mt-0.5">
                      Published on {new Date(classTimetable.published_at).toLocaleDateString()} &bull; Total {classTimetable.entries.length} weekly sessions
                    </p>
                  )}
                </div>

                {!classTimetable.has_timetable && (
                  <button
                    onClick={() => setActiveTab('personal')}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 transition-colors"
                  >
                    Go to Personal Schedule &rarr;
                  </button>
                )}
              </div>

              {!classTimetable.has_timetable ? (
                /* No Timetable Published Yet */
                <div className="p-12 rounded-2xl bg-black/40 border border-white/10 text-center space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-white/5 text-slate-400 flex items-center justify-center mx-auto border border-white/10">
                    <Clock size={24} />
                  </div>
                  <h3 className="text-base font-bold text-white">No Official Timetable Published Yet</h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Your class administrator hasn't published an official weekly schedule for{' '}
                    <strong className="text-emerald-400">{classTimetable.cohort_name}</strong> yet.
                    It will appear here automatically once published.
                  </p>
                  <div className="pt-2">
                    <button
                      onClick={() => setActiveTab('personal')}
                      className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs rounded-xl transition-all shadow-lg shadow-emerald-500/20"
                    >
                      Open Personal Schedule
                    </button>
                  </div>
                </div>
              ) : (
                /* Published Schedule Grid by Day */
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {DAYS.map((day) => {
                    const daySlots = classEntriesByDay[day.value] || []
                    return (
                      <div
                        key={day.value}
                        className={`p-4 rounded-xl border backdrop-blur-md flex flex-col transition-all ${
                          daySlots.length > 0
                            ? 'bg-black/50 border-emerald-500/30'
                            : 'bg-black/20 border-white/5 opacity-70'
                        }`}
                      >
                        <div className="flex items-center justify-between pb-3 mb-3 border-b border-white/10">
                          <h4 className="font-bold text-sm text-white flex items-center gap-2">
                            <span>{day.label}</span>
                          </h4>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                              daySlots.length > 0
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-white/5 text-slate-500'
                            }`}
                          >
                            {daySlots.length} {daySlots.length === 1 ? 'class' : 'classes'}
                          </span>
                        </div>

                        {daySlots.length === 0 ? (
                          <div className="py-8 text-center text-xs text-slate-500">
                            No classes scheduled
                          </div>
                        ) : (
                          <div className="space-y-2.5">
                            {daySlots.map((slot, idx) => (
                              <div
                                key={idx}
                                className="p-3 rounded-lg bg-white/[0.03] hover:bg-emerald-500/[0.06] border border-white/5 hover:border-emerald-500/30 transition-all space-y-1.5"
                              >
                                <div className="flex items-center justify-between text-xs">
                                  <span className="font-mono font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 text-[11px]">
                                    {slot.start_time} – {slot.end_time}
                                  </span>
                                  {slot.room && (
                                    <span className="text-[11px] text-slate-400 font-medium">
                                      {slot.room}
                                    </span>
                                  )}
                                </div>

                                <h5 className="font-bold text-white text-sm tracking-tight">
                                  {slot.subject}
                                </h5>

                                {slot.teacher && (
                                  <p className="text-[11px] text-slate-400 flex items-center gap-1">
                                    <User size={11} className="text-slate-500" />
                                    <span>{slot.teacher}</span>
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* ─────────────────────────────────────────────────────────────
              VIEW 2: PERSONAL SCHEDULE (Custom)
          ───────────────────────────────────────────────────────────── */}
          {(activeTab === 'personal' || !classTimetable.enrolled) && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/10">
                <div>
                  <h2 className="text-lg font-bold text-white">Personal Schedule</h2>
                  <p className="text-xs text-slate-400">
                    Customize your personal timetable entries, study sessions, and self-managed slots.
                  </p>
                </div>

                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex items-center gap-1 bg-black/40 backdrop-blur-md border border-white/10 rounded-lg p-1">
                    <button
                      onClick={() => setView('grid')}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                        view === 'grid' ? 'bg-emerald-500 text-black font-bold' : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      <Grid3X3 size={14} /> Grid
                    </button>
                    <button
                      onClick={() => setView('list')}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                        view === 'list' ? 'bg-emerald-500 text-black font-bold' : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      <List size={14} /> List
                    </button>
                  </div>

                  <button
                    onClick={() => setShowUpload(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-black font-semibold rounded-xl text-xs transition-all shadow-lg shadow-emerald-500/20"
                  >
                    <Upload size={14} /> Upload Personal Timetable
                  </button>

                  <button
                    onClick={handleSave}
                    disabled={saving || !entries.length}
                    className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 hover:bg-white/10 text-white font-semibold rounded-xl text-xs transition-all disabled:opacity-50"
                  >
                    <Save size={14} /> {saving ? 'Saving...' : 'Save Schedule'}
                  </button>
                </div>
              </div>

              {view === 'grid' ? (
                <TimetableGridView entries={entries} />
              ) : (
                <TimetableListEditor entries={entries} subjects={subjects} onChange={setEntries} />
              )}
            </div>
          )}
        </div>
      )}

      {showUpload && (
        <UploadTimetable
          onClose={() => setShowUpload(false)}
          onExtracted={async (extractedEntries) => {
            setShowUpload(false)
            setSaving(true)
            try {
              const payload = extractedEntries.map((e) => ({
                subject_id: e.subject_id,
                day_of_week: Number(e.day_of_week),
                start_time: e.start_time,
                end_time: e.end_time,
                room: e.room || null,
                notes: e.notes || null,
              }))
              await bulkSaveTimetableEntries(payload)
              const { data: refreshed } = await getTimetableEntries()
              setEntries(refreshed)
              toast.success('Timetable saved automatically')
            } catch {
              setEntries(extractedEntries)
              toast.error('Could not auto-save — click Save Schedule manually')
            } finally {
              setSaving(false)
            }
          }}
        />
      )}
    </div>
  )
}
