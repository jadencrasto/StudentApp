import { useEffect, useMemo, useState } from 'react'
import { Grid3X3, List, Save, Upload } from 'lucide-react'
import toast from 'react-hot-toast'

import TimetableGridView from '../components/timetable/TimetableGridView'
import TimetableListEditor from '../components/timetable/TimetableListEditor'
import UploadTimetable from '../components/timetable/UploadTimetable'
import { getSubjects } from '../api/attendance'
import { bulkSaveTimetableEntries, getTimetableEntries } from '../api/timetable'

export default function TimetableSetupPage() {
  const [view, setView] = useState('grid')
  const [entries, setEntries] = useState([])
  const [subjects, setSubjects] = useState([])
  const [showUpload, setShowUpload] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const [{ data: timetable }, { data: subjectList }] = await Promise.all([
          getTimetableEntries(),
          getSubjects(),
        ])
        setEntries(timetable)
        setSubjects(subjectList)
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
      toast.success('Timetable saved successfully')
      // Re-fetch from DB so the grid reflects the actual saved state
      const { data: refreshed } = await getTimetableEntries()
      setEntries(refreshed)
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save timetable')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 lg:p-8">
      {loading ? (
        <div className="flex items-center justify-center py-32">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-6">
          <div>
            <h1 className="font-display text-3xl text-white mb-1">Weekly Timetable</h1>
            <p className="text-slate-400 text-sm">Manage your class schedule with AI-powered extraction</p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1 bg-black/40 backdrop-blur-md border border-white/10 rounded-lg p-1">
              <button
                onClick={() => setView('grid')}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all ${
                  view === 'grid' ? 'bg-emerald-500 text-black' : 'text-gray-400 hover:text-white'
                }`}
              >
                <Grid3X3 size={16} /> Grid
              </button>
              <button
                onClick={() => setView('list')}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all ${
                  view === 'list' ? 'bg-emerald-500 text-black' : 'text-gray-400 hover:text-white'
                }`}
              >
                <List size={16} /> List
              </button>
            </div>

            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-black font-semibold rounded-xl transition-all shadow-lg shadow-emerald-500/20"
            >
              <Upload size={18} /> Upload Timetable
            </button>

            <button
              onClick={handleSave}
              disabled={saving || !entries.length}
              className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 hover:bg-white/10 text-white font-semibold rounded-xl transition-all disabled:opacity-50"
            >
              <Save size={16} /> {saving ? 'Saving...' : 'Save Schedule'}
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

      {showUpload && (
        <UploadTimetable
          onClose={() => setShowUpload(false)}
          onExtracted={async (extractedEntries) => {
            setShowUpload(false)
            // Auto-save extracted entries to DB, then reload
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
              // If auto-save fails, still show extracted entries
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
