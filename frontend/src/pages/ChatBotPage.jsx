/**
 * ChatBotPage — AI Study Assistant & Viva Examiner
 *
 * Two modes:
 *   • General Q&A — ask anything academic
 *   • Viva — AI generates questions on uploaded documents and evaluates answers
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  createConversation, listConversations, getConversation,
  deleteConversation, sendMessage, startViva,
} from '../api/chat'
import { documentsAPI } from '../lib/api'
import toast from 'react-hot-toast'
import {
  MessageSquare, Send, Plus, Trash2, Bot, User, FileText,
  BookOpen, Loader2, Sparkles, GraduationCap, ChevronDown,
} from 'lucide-react'

// ─── Markdown renderer (handles code blocks, HTML escaping, etc.) ───

function renderMarkdown(text) {
  if (!text) return ''

  // 1. Extract fenced code blocks first to protect them
  const codeBlocks = []
  let processed = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length
    codeBlocks.push({ lang, code })
    return `%%CODEBLOCK_${idx}%%`
  })

  // 2. Extract inline code to protect it
  const inlineCodes = []
  processed = processed.replace(/`([^`]+)`/g, (_, code) => {
    const idx = inlineCodes.length
    inlineCodes.push(code)
    return `%%INLINE_${idx}%%`
  })

  // 3. Escape HTML entities so tags like <div> display as text
  processed = processed
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 4. Markdown formatting
  processed = processed
    // Bold & italic
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-slate-100">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Headings
    .replace(/^### (.+)$/gm, '<h3 class="font-semibold text-emerald-400 mt-3 mb-1 text-sm">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="font-semibold text-emerald-400 mt-3 mb-1 text-base">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="font-bold text-emerald-400 mt-4 mb-1.5 text-lg">$1</h1>')
    // Bullet lists
    .replace(/^[-•]\s+(.+)$/gm, '<div class="flex gap-2 ml-2 my-0.5"><span class="text-emerald-400/60 select-none">•</span><span>$1</span></div>')
    // Numbered lists
    .replace(/^(\d+)\.\s+(.+)$/gm, '<div class="flex gap-2 ml-2 my-0.5"><span class="text-emerald-400/60 font-mono text-xs min-w-[1.2em] select-none">$1.</span><span>$2</span></div>')
    // Horizontal rule
    .replace(/^---+$/gm, '<hr class="border-white/10 my-3"/>')
    // Line breaks
    .replace(/\n{2,}/g, '<div class="h-3"></div>')
    .replace(/\n/g, '<br/>')

  // 5. Restore inline code with styling
  processed = processed.replace(/%%INLINE_(\d+)%%/g, (_, idx) => {
    const code = inlineCodes[+idx]
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<code class="bg-black/40 text-emerald-300 px-1.5 py-0.5 rounded text-xs font-mono border border-white/5">${code}</code>`
  })

  // 6. Restore fenced code blocks with styling
  processed = processed.replace(/%%CODEBLOCK_(\d+)%%/g, (_, idx) => {
    const { lang, code } = codeBlocks[+idx]
    const escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .trim()
    const langLabel = lang ? `<div class="text-[10px] text-slate-500 font-mono mb-1 select-none">${lang}</div>` : ''
    return `<div class="bg-black/80 border border-white/10 rounded-lg p-3 my-2 overflow-x-auto">${langLabel}<pre class="text-xs font-mono text-gray-300 whitespace-pre-wrap leading-relaxed">${escaped}</pre></div>`
  })

  return processed
}

// ─── Single chat bubble ─────────────────────────────────────

function ChatBubble({ role, content }) {
  const isUser = role === 'user'
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, x: isUser ? 12 : -12 }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar */}
      <motion.div
        initial={{ scale: 0.5 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: 'spring', stiffness: 400 }}
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-emerald-500 text-black' : 'bg-white/5 text-emerald-400'
        }`}
      >
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </motion.div>
      {/* Message */}
      <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-emerald-500/10 border border-emerald-500/20 text-slate-200'
            : 'bg-white/[0.02] border border-white/5 text-slate-300'
      }`}>
        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
      </div>
    </motion.div>
  )
}

// ─── Conversation list sidebar ──────────────────────────────

function ConversationList({ conversations, activeId, onSelect, onDelete, onCreate }) {
  return (
    <div className="flex flex-col h-full">
      {/* New chat button */}
      <button
        onClick={onCreate}
        className="flex items-center gap-2 mx-3 mt-3 mb-2 px-3 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-medium hover:bg-emerald-500/20 transition-all"
      >
        <Plus size={15} /> New Chat
      </button>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1 py-1">
        {conversations.map((c) => (
          <div
            key={c.id}
            className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all text-sm ${
              c.id === activeId
                ? 'bg-white/10 text-white'
                : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
            }`}
            onClick={() => onSelect(c.id)}
          >
            {c.mode === 'viva' ? <GraduationCap size={14} /> : <MessageSquare size={14} />}
            <span className="flex-1 truncate">{c.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(c.id) }}
              className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-opacity"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        {conversations.length === 0 && (
          <p className="text-slate-600 text-xs text-center py-6">No conversations yet</p>
        )}
      </div>
    </div>
  )
}

// ─── Viva start modal ───────────────────────────────────────

function VivaModal({ open, onClose, onStart }) {
  const [docs, setDocs] = useState([])
  const [selectedDoc, setSelectedDoc] = useState('')
  const [numQ, setNumQ] = useState(5)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      documentsAPI.list()
        .then(r => setDocs(Array.isArray(r.data) ? r.data : []))
        .catch(() => toast.error('Failed to load documents'))
    }
  }, [open])

  if (!open) return null

  const handleStart = async () => {
    if (!selectedDoc) return toast.error('Select a document')
    setLoading(true)
    try {
      await onStart(selectedDoc, numQ)
      onClose()
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to start viva')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-black/90 border border-white/10 rounded-2xl w-full max-w-md shadow-xl backdrop-blur-md">
        <div className="px-5 py-4 border-b border-white/10">
          <h2 className="text-white font-semibold flex items-center gap-2">
            <GraduationCap size={18} className="text-emerald-400" />
            Start Viva Session
          </h2>
          <p className="text-slate-500 text-xs mt-1">
            AI will generate questions based on your uploaded document
          </p>
        </div>
        <div className="p-5 space-y-4">
          {/* Document picker */}
          <div>
            <label className="text-slate-400 text-xs font-medium block mb-1">Select Document</label>
            <div className="relative">
              <select
                value={selectedDoc}
                onChange={(e) => setSelectedDoc(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2.5 text-slate-200 text-sm focus:border-emerald-500 focus:outline-none appearance-none"
              >
                <option value="">Choose a document…</option>
                {docs.filter(d => d.extraction_status === 'done').map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.original_filename || 'Untitled'} ({d.file_type})
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-3 top-3 text-slate-500 pointer-events-none" />
            </div>
          </div>

          {/* Number of questions */}
          <div>
            <label className="text-slate-400 text-xs font-medium block mb-1">
              Number of Questions: <span className="text-emerald-400">{numQ}</span>
            </label>
            <input
              type="range"
              min={1} max={15} value={numQ}
              onChange={(e) => setNumQ(+e.target.value)}
              className="w-full accent-emerald-500"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button onClick={onClose} className="flex-1 px-4 py-2.5 rounded-xl text-sm text-slate-400 border border-white/10 bg-white/5 hover:bg-white/10 transition-colors">
              Cancel
            </button>
            <button
              onClick={handleStart}
              disabled={loading || !selectedDoc}
              className="flex-1 px-4 py-2.5 rounded-xl text-sm font-medium bg-emerald-500 text-black hover:bg-emerald-600 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {loading ? 'Generating…' : 'Start Viva'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════
//  Main Page
// ═════════════════════════════════════════════════════════════

export default function ChatBotPage() {
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [vivaOpen, setVivaOpen] = useState(false)
  const [activeMode, setActiveMode] = useState('general')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // ── Load conversations on mount ────────────────────────────

  const loadConversations = useCallback(async () => {
    try {
      const list = await listConversations()
      setConversations(list)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    loadConversations().then(() => setLoading(false))
  }, [loadConversations])

  // ── Auto-scroll to bottom ─────────────────────────────────

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Select conversation ───────────────────────────────────

  const selectConversation = useCallback(async (id) => {
    try {
      const conv = await getConversation(id)
      setActiveConvId(id)
      setMessages(conv.messages || [])
      setActiveMode(conv.mode || 'general')
    } catch {
      toast.error('Failed to load conversation')
    }
  }, [])

  // ── Create new conversation ───────────────────────────────

  const handleNew = useCallback(async () => {
    try {
      const conv = await createConversation({ mode: 'general' })
      await loadConversations()
      setActiveConvId(conv.id)
      setMessages([])
      setActiveMode('general')
      inputRef.current?.focus()
    } catch {
      toast.error('Failed to create conversation')
    }
  }, [loadConversations])

  // ── Delete conversation ───────────────────────────────────

  const handleDelete = useCallback(async (id) => {
    try {
      await deleteConversation(id)
      if (activeConvId === id) {
        setActiveConvId(null)
        setMessages([])
      }
      await loadConversations()
      toast.success('Conversation deleted')
    } catch {
      toast.error('Failed to delete')
    }
  }, [activeConvId, loadConversations])

  // ── Send message ──────────────────────────────────────────

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return

    // Auto-create conversation if none active
    let convId = activeConvId
    if (!convId) {
      try {
        const conv = await createConversation({ mode: 'general' })
        convId = conv.id
        setActiveConvId(conv.id)
        await loadConversations()
      } catch {
        toast.error('Failed to create conversation')
        return
      }
    }

    // Optimistically add user message
    const tempUserMsg = { id: 'temp-user', role: 'user', content: text, created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, tempUserMsg])
    setInput('')
    setSending(true)

    try {
      const aiMsg = await sendMessage(convId, text)
      // Replace temp and add AI response
      setMessages((prev) => {
        const withoutTemp = prev.filter((m) => m.id !== 'temp-user')
        return [...withoutTemp, { id: 'real-user-' + Date.now(), role: 'user', content: text, created_at: new Date().toISOString() }, aiMsg]
      })
      await loadConversations() // refresh titles
    } catch (e) {
      toast.error('Failed to send message')
      setMessages((prev) => prev.filter((m) => m.id !== 'temp-user'))
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }, [input, sending, activeConvId, loadConversations])

  // ── Start viva ────────────────────────────────────────────

  const handleStartViva = useCallback(async (docId, numQ) => {
    const conv = await startViva(docId, numQ)
    await loadConversations()
    setActiveConvId(conv.id)
    setMessages(conv.messages || [])
    setActiveMode('viva')
  }, [loadConversations])

  // ── Keyboard ──────────────────────────────────────────────

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── Render ────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 size={32} className="animate-spin text-emerald-500" />
      </div>
    )
  }

  return (
    <div className="flex h-screen p-6 gap-0">
      {/* ── Sidebar ── */}
      <div className="w-64 bg-white/[0.02] border border-white/10 rounded-l-2xl flex flex-col backdrop-blur-md">
        <div className="px-4 py-3 border-b border-white/10">
          <h2 className="text-white font-semibold text-sm flex items-center gap-2">
            <Bot size={16} className="text-emerald-500" />
            SAIS Chatbot
          </h2>
        </div>
        <ConversationList
          conversations={conversations}
          activeId={activeConvId}
          onSelect={selectConversation}
          onDelete={handleDelete}
          onCreate={handleNew}
        />
        {/* Viva button */}
        <div className="px-3 pb-3">
          <button
            onClick={() => setVivaOpen(true)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium bg-gradient-to-r from-blue-500/20 to-emerald-500/20 border border-white/10 text-emerald-300 hover:text-emerald-400 hover:border-emerald-500/30 transition-all"
          >
            <GraduationCap size={15} />
            Start Viva
          </button>
        </div>
      </div>

      {/* ── Main chat area ── */}
      <div className="flex-1 flex flex-col bg-black rounded-r-2xl border-y border-r border-white/10">
        {/* Header */}
        <div className="px-6 py-3 border-b border-white/10 flex items-center gap-3">
          {activeMode === 'viva' ? (
            <GraduationCap size={18} className="text-emerald-400" />
          ) : (
            <Sparkles size={18} className="text-emerald-500" />
          )}
          <h3 className="text-white text-sm font-medium">
            {activeConvId
              ? conversations.find((c) => c.id === activeConvId)?.title || 'Chat'
              : 'Start a conversation'}
          </h3>
          {activeMode === 'viva' && (
            <span className="text-xs bg-emerald-400/10 text-emerald-400 px-2 py-0.5 rounded-lg border border-emerald-400/20">Viva Mode</span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 && !activeConvId && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center mb-4">
                <Bot size={28} className="text-emerald-500" />
              </div>
              <h3 className="text-white font-semibold text-lg mb-2">SAIS Study Assistant</h3>
              <p className="text-slate-400 text-sm max-w-md mb-6">
                Ask any academic question, or start a <strong className="text-emerald-400">Viva session</strong> to
                test your knowledge on uploaded documents.
              </p>
              <div className="grid grid-cols-2 gap-3 max-w-sm w-full">
                {[
                  { icon: MessageSquare, label: 'Ask a question', hint: 'Explain binary search…' },
                  { icon: BookOpen, label: 'Summarize a topic', hint: 'What is photosynthesis?'   },
                  { icon: FileText, label: 'Help with assignment', hint: 'How to solve this…'     },
                  { icon: GraduationCap, label: 'Viva practice', hint: 'Test my knowledge'        },
                ].map(({ icon: Icon, label, hint }, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      if (i === 3) { setVivaOpen(true); return }
                      handleNew()
                    }}
                    className="text-left px-4 py-3 rounded-xl bg-white/[0.02] border border-white/5 hover:border-emerald-500/30 hover:bg-white/5 transition-all group"
                  >
                    <Icon size={16} className="text-slate-500 group-hover:text-emerald-500 mb-1.5 transition-colors" />
                    <p className="text-slate-300 text-xs font-medium">{label}</p>
                    <p className="text-slate-600 text-[10px] mt-0.5">{hint}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.length === 0 && activeConvId && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Bot size={32} className="text-slate-600 mb-3" />
              <p className="text-slate-500 text-sm">Send a message to start the conversation</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatBubble key={msg.id || i} role={msg.role} content={msg.content} />
          ))}
          {sending && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
                <Bot size={15} className="text-emerald-500" />
              </div>
              <div className="bg-white/[0.02] border border-white/5 rounded-2xl px-4 py-3">
                <div className="flex items-center gap-2 text-slate-500 text-sm">
                  <Loader2 size={14} className="animate-spin" />
                  Thinking…
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-6 py-4 border-t border-white/10">
          <div className="flex items-end gap-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={activeMode === 'viva' ? 'Type your answer…' : 'Ask anything…'}
              rows={1}
              className="flex-1 bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/30 transition-colors"
              style={{ minHeight: '44px', maxHeight: '120px' }}
              onInput={(e) => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px' }}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="h-11 w-11 rounded-xl bg-emerald-500 text-black flex items-center justify-center hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-slate-600 text-[10px] mt-2 text-center">
            Powered by Ollama • SAIS AI Study Assistant
          </p>
        </div>
      </div>

      {/* Viva modal */}
      <VivaModal open={vivaOpen} onClose={() => setVivaOpen(false)} onStart={handleStartViva} />
    </div>
  )
}
