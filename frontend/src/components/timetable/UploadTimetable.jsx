import { useRef, useState } from 'react'
import { CheckCircle, Loader2, Sparkles, Upload, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { uploadTimetable } from '../../api/timetable'

const DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function UploadTimetable({ onClose, onExtracted }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [extracting, setExtracting] = useState(false)
  const [result, setResult] = useState(null)
  const inputRef = useRef(null)

  function handleFileSelect(event) {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) return

    setFile(selectedFile)
    setResult(null)

    if (selectedFile.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = (e) => setPreview(e.target?.result)
      reader.readAsDataURL(selectedFile)
    } else {
      setPreview(null)
    }
  }

  async function handleExtract() {
    if (!file) return

    setExtracting(true)
    const formData = new FormData()
    formData.append('file', file)

    try {
      const { data } = await uploadTimetable(formData)
      if (data.status !== 'success') {
        toast.error(data.error || 'AI extraction failed')
        return
      }

      setResult(data)
      toast.success(`Extracted ${data.entries.length} timetable entr${data.entries.length === 1 ? 'y' : 'ies'}`)
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to extract timetable')
    } finally {
      setExtracting(false)
    }
  }

  function handleUseExtracted() {
    if (!result?.entries?.length) {
      toast.error('No entries to use')
      return
    }
    onExtracted(result.entries)
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900/90 backdrop-blur-xl border border-slate-800/50 rounded-2xl max-w-2xl w-full p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-amber-400/20 rounded-xl flex items-center justify-center">
              <Sparkles size={20} className="text-amber-400" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">AI Timetable Extraction</h3>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X size={22} />
          </button>
        </div>

        {!file ? (
          <label className="block border-2 border-dashed border-slate-700 hover:border-amber-400/50 rounded-xl p-12 text-center cursor-pointer transition-all group">
            <input
              ref={inputRef}
              type="file"
              accept="image/*,.pdf"
              onChange={handleFileSelect}
              className="hidden"
            />
            <Upload size={44} className="mx-auto text-slate-600 group-hover:text-amber-400 transition-colors mb-4" />
            <p className="text-slate-300 mb-2">Drop timetable image/PDF here or click to browse</p>
            <p className="text-xs text-slate-500">Supports PNG, JPG, JPEG, PDF</p>
          </label>
        ) : !result ? (
          <div>
            {preview ? (
              <img
                src={preview}
                alt="Timetable preview"
                className="w-full h-64 object-contain bg-slate-800/50 rounded-lg mb-4"
              />
            ) : (
              <div className="w-full h-52 flex items-center justify-center bg-slate-800/50 rounded-lg mb-4 text-slate-400 text-sm">
                PDF selected: {file.name}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => {
                  setFile(null)
                  setPreview(null)
                  if (inputRef.current) inputRef.current.value = ''
                }}
                className="py-3 border border-slate-700 rounded-xl text-slate-300 hover:bg-slate-800 transition-all"
              >
                Change File
              </button>
              <button
                onClick={handleExtract}
                disabled={extracting}
                className="py-3 flex items-center justify-center gap-2 bg-gradient-to-r from-amber-400 to-orange-500 hover:from-amber-300 hover:to-orange-400 text-slate-900 font-semibold rounded-xl transition-all disabled:opacity-50"
              >
                {extracting ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Extracting...
                  </>
                ) : (
                  <>
                    <Sparkles size={18} />
                    Extract Schedule
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="mb-4 p-4 bg-emerald-400/10 border border-emerald-400/30 rounded-lg">
              <div className="flex items-center gap-2 text-emerald-400 mb-1">
                <CheckCircle size={18} />
                <span className="font-semibold">Extraction Successful</span>
              </div>
              <p className="text-sm text-emerald-300">
                Found {result.entries.length} classes • {(Number(result.confidence || 0) * 100).toFixed(0)}% confidence
              </p>
            </div>

            <div className="max-h-64 overflow-y-auto space-y-2 mb-4">
              {result.entries.map((entry, index) => (
                <div key={index} className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg text-sm border border-slate-700/40">
                  <div>
                    <p className="text-white font-medium">{entry.subject}</p>
                    <p className="text-xs text-slate-400">
                      {DAY_SHORT[entry.day_of_week]} • {entry.start_time}-{entry.end_time}
                    </p>
                  </div>
                  {entry.room && <span className="text-xs text-slate-500">{entry.room}</span>}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={onClose}
                className="py-3 border border-slate-700 rounded-xl text-slate-300 hover:bg-slate-800 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleUseExtracted}
                className="py-3 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-all"
              >
                Use Extracted Entries
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
