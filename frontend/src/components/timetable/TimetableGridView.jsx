import { motion } from 'framer-motion'
import { Clock, MapPin } from 'lucide-react'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const ease = [0.4, 0, 0.2, 1]

export default function TimetableGridView({ entries }) {
  const timeSlots = []
  for (let hour = 8; hour <= 20; hour++) {
    timeSlots.push(`${String(hour).padStart(2, '0')}:00`)
  }

  const entriesByDay = DAYS.map((_, dayIndex) =>
    entries.filter((entry) => entry.day_of_week === dayIndex)
  )

  function getGridRow(startTime, endTime) {
    const [startHour, startMinute] = startTime.split(':').map(Number)
    const [endHour, endMinute] = endTime.split(':').map(Number)

    const startRow = (startHour - 8) * 2 + (startMinute >= 30 ? 2 : 1) + 2
    const endRow = (endHour - 8) * 2 + (endMinute >= 30 ? 2 : 1) + 2

    return `${Math.max(startRow, 2)} / ${Math.max(endRow, startRow + 1)}`
  }

  let entryCounter = 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease }}
      className="bg-slate-900/50 backdrop-blur-md border border-slate-800/50 rounded-2xl p-4 lg:p-6 overflow-x-auto"
    >
      <div
        className="grid gap-2 min-w-[900px]"
        style={{
          gridTemplateColumns: '72px repeat(7, minmax(0, 1fr))',
          gridTemplateRows: `auto repeat(${timeSlots.length * 2}, minmax(24px, 1fr))`,
        }}
      >
        <div className="border-b border-slate-800/50 p-2" />

        {DAYS.map((day, i) => (
          <motion.div
            key={day}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.05 * i, ease }}
            className="text-center font-semibold text-sm text-amber-400 border-b border-slate-800/50 p-2"
          >
            {day.slice(0, 3)}
          </motion.div>
        ))}

        {timeSlots.map((time, index) => (
          <div
            key={time}
            className="text-xs text-slate-500 p-2 border-r border-slate-800/40"
            style={{ gridRow: `${index * 2 + 2} / span 2` }}
          >
            {time}
          </div>
        ))}

        {entriesByDay.map((dayEntries, dayIndex) =>
          dayEntries.map((entry) => {
            const idx = entryCounter++
            return (
              <motion.div
                key={entry.id || `${entry.subject_id}-${entry.day_of_week}-${entry.start_time}`}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.35, delay: 0.03 * idx + 0.3, ease }}
                whileHover={{ scale: 1.03, zIndex: 10 }}
                className="relative group"
                style={{
                  gridColumn: dayIndex + 2,
                  gridRow: getGridRow(entry.start_time, entry.end_time),
                }}
              >
                <div className="h-full p-2 rounded-lg bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-sm border border-slate-700/40 border-l-4 border-l-amber-400 hover:border-l-amber-300 transition-all duration-200 hover:shadow-lg hover:shadow-amber-400/20">
                  <p className="text-xs font-semibold text-white truncate">
                    {entry.subject_name || entry.subject || 'Untitled class'}
                  </p>
                  <div className="flex items-center gap-1 mt-1 text-xs text-slate-400">
                    <Clock size={10} />
                    <span>{entry.start_time} - {entry.end_time}</span>
                  </div>
                  {entry.room && (
                    <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-500">
                      <MapPin size={10} />
                      <span className="truncate">{entry.room}</span>
                    </div>
                  )}
                </div>
              </motion.div>
            )
          })
        )}
      </div>
    </motion.div>
  )
}
