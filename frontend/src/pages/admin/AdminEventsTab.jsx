import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CalendarDays, Plus, RefreshCw, Eye, EyeOff, Edit2, Globe,
  AlertCircle, CheckCircle2, Clock, Search, Filter, X, ExternalLink
} from 'lucide-react';
import toast from 'react-hot-toast';
import client from '../../api/client';

const EVENT_TYPES = ['Notice', 'Exam', 'Event', 'Holiday', 'Lecture'];

const TYPE_BADGES = {
  Notice:  'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  Exam:    'bg-red-500/15 text-red-400 border-red-500/30',
  Event:   'bg-blue-500/15 text-blue-400 border-blue-500/30',
  Holiday: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  Lecture: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
};

export default function AdminEventsTab() {
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState([]);
  const [needsDate, setNeedsDate] = useState([]);
  const [stats, setStats] = useState({ total: 0, dated_count: 0, needs_date_count: 0, hidden_count: 0 });

  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('All');

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showScrapeModal, setShowScrapeModal] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);

  // Form states
  const [addForm, setAddForm] = useState({
    event_name: '',
    event_type: 'Event',
    event_date: '',
    semester: '',
    department: '',
    source_url: '',
  });
  const [addLoading, setAddLoading] = useState(false);

  const [scrapeForm, setScrapeForm] = useState({
    college_url: '',
    college_name: '',
  });
  const [scrapeLoading, setScrapeLoading] = useState(false);

  const [editForm, setEditForm] = useState({
    event_name: '',
    event_type: 'Event',
    event_date: '',
    semester: '',
    department: '',
  });
  const [editLoading, setEditLoading] = useState(false);

  useEffect(() => {
    loadEvents();
  }, []);

  async function loadEvents() {
    setLoading(true);
    try {
      const { data } = await client.get('/admin/events');
      setEvents(data.events || []);
      setNeedsDate(data.needs_date || []);
      setStats(data.stats || { total: 0, dated_count: 0, needs_date_count: 0, hidden_count: 0 });
    } catch (err) {
      toast.error('Failed to load college events');
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleHide(eventItem) {
    const newStatus = !eventItem.is_hidden;
    try {
      await client.patch(`/admin/events/${eventItem.id}`, { is_hidden: newStatus });
      toast.success(newStatus ? 'Event hidden from students' : 'Event now visible to students');
      loadEvents();
    } catch (err) {
      toast.error('Failed to update event visibility');
    }
  }

  async function handleAddEvent(e) {
    e.preventDefault();
    if (!addForm.event_name.trim()) {
      toast.error('Please enter an event name');
      return;
    }
    setAddLoading(true);
    try {
      await client.post('/admin/events/manual', {
        ...addForm,
        event_name: addForm.event_name.trim(),
        event_date: addForm.event_date.trim() || null,
      });
      toast.success('Event added successfully');
      setShowAddModal(false);
      setAddForm({ event_name: '', event_type: 'Event', event_date: '', semester: '', department: '', source_url: '' });
      loadEvents();
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to create event';
      toast.error(msg);
    } finally {
      setAddLoading(false);
    }
  }

  async function handleTriggerScrape(e) {
    e.preventDefault();
    if (!scrapeForm.college_url.trim()) {
      toast.error('Please enter a website URL');
      return;
    }
    setScrapeLoading(true);
    try {
      const { data } = await client.post('/admin/events/scrape', {
        college_url: scrapeForm.college_url.trim(),
        college_name: scrapeForm.college_name.trim() || 'College',
      });
      toast.success(data.message || 'Scraping completed');
      setShowScrapeModal(false);
      setScrapeForm({ college_url: '', college_name: '' });
      loadEvents();
    } catch (err) {
      const msg = err.response?.data?.detail || 'Scraping failed';
      toast.error(msg);
    } finally {
      setScrapeLoading(false);
    }
  }

  async function handleSaveEdit(e) {
    e.preventDefault();
    if (!editForm.event_name.trim()) {
      toast.error('Event title cannot be empty');
      return;
    }
    setEditLoading(true);
    try {
      await client.patch(`/admin/events/${editingEvent.id}`, {
        ...editForm,
        event_date: editForm.event_date.trim() || null,
      });
      toast.success('Event updated successfully');
      setEditingEvent(null);
      loadEvents();
    } catch (err) {
      toast.error('Failed to update event');
    } finally {
      setEditLoading(false);
    }
  }

  function openEditModal(eventItem) {
    setEditingEvent(eventItem);
    setEditForm({
      event_name: eventItem.event_name || '',
      event_type: eventItem.event_type || 'Event',
      event_date: eventItem.event_date || '',
      semester: eventItem.semester || '',
      department: eventItem.department || '',
    });
  }

  const filteredDated = events.filter(e => {
    if (typeFilter !== 'All' && e.event_type !== typeFilter) return false;
    if (search.trim() && !e.event_name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const filteredNeedsDate = needsDate.filter(e => {
    if (typeFilter !== 'All' && e.event_type !== typeFilter) return false;
    if (search.trim() && !e.event_name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* ── Top Bar ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <CalendarDays className="text-emerald-400" size={22} />
            College Events Management
          </h2>
          <p className="text-slate-400 text-xs mt-0.5">
            Manage academic notices, exams, and event schedules for your institution.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowScrapeModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-white border border-white/10 rounded-xl text-xs font-semibold transition-all shadow-sm"
          >
            <Globe size={14} className="text-blue-400" />
            Scrape Website
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-emerald-500 hover:bg-emerald-400 text-black rounded-xl text-xs font-bold transition-all shadow-sm"
          >
            <Plus size={14} />
            Add Event
          </button>
          <button
            onClick={loadEvents}
            disabled={loading}
            className="p-2 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl border border-white/10 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* ── Stats Overview ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-black/40 border border-white/10 rounded-xl p-3.5">
          <span className="text-slate-400 text-xs font-medium">Total Events</span>
          <div className="text-xl font-bold text-white mt-0.5">{stats.total}</div>
        </div>
        <div className="bg-black/40 border border-white/10 rounded-xl p-3.5">
          <span className="text-emerald-400 text-xs font-medium">Dated (Student Visible)</span>
          <div className="text-xl font-bold text-emerald-400 mt-0.5">{stats.dated_count - stats.hidden_count}</div>
        </div>
        <div className="bg-black/40 border border-amber-500/20 bg-amber-500/5 rounded-xl p-3.5">
          <span className="text-amber-400 text-xs font-medium">Needs a Date</span>
          <div className="text-xl font-bold text-amber-400 mt-0.5">{stats.needs_date_count}</div>
        </div>
        <div className="bg-black/40 border border-white/10 rounded-xl p-3.5">
          <span className="text-slate-400 text-xs font-medium">Hidden</span>
          <div className="text-xl font-bold text-slate-300 mt-0.5">{stats.hidden_count}</div>
        </div>
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search events by title..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-black/40 border border-white/10 rounded-xl pl-9 pr-3.5 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          {['All', ...EVENT_TYPES].map(type => (
            <button
              key={type}
              onClick={() => setTypeFilter(type)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-colors ${
                typeFilter === type
                  ? 'bg-emerald-500 text-black font-bold'
                  : 'bg-white/5 hover:bg-white/10 text-slate-400 border border-white/5'
              }`}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      {/* ── Section 1: "Needs a Date" (Undated Events) ───────────────────── */}
      {filteredNeedsDate.length > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-5 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-amber-400 flex items-center gap-1.5">
                <Clock size={16} />
                Needs a Date ({filteredNeedsDate.length})
              </h3>
              <p className="text-slate-400 text-xs mt-0.5">
                These events were detected without a specific date. They are hidden from students until a date is assigned. You can add a date, hide, or leave them as reference.
              </p>
            </div>
          </div>

          <div className="space-y-2 mt-2">
            {filteredNeedsDate.map(item => (
              <div
                key={item.id}
                className="bg-black/50 border border-white/10 rounded-xl p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="space-y-1 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${TYPE_BADGES[item.event_type] || TYPE_BADGES.Notice}`}>
                      {item.event_type}
                    </span>
                    {item.is_manual ? (
                      <span className="bg-purple-500/15 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded-full text-[10px] font-bold">
                        Manual
                      </span>
                    ) : (
                      <span className="bg-blue-500/10 text-blue-300 border border-blue-500/20 px-2 py-0.5 rounded-full text-[10px]">
                        Scraped
                      </span>
                    )}
                    {item.is_hidden && (
                      <span className="bg-red-500/15 text-red-400 border border-red-500/30 px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1">
                        <EyeOff size={10} /> Hidden
                      </span>
                    )}
                    {item.semester && <span className="text-slate-500 text-xs">Sem: {item.semester}</span>}
                    {item.department && <span className="text-slate-500 text-xs">Dept: {item.department}</span>}
                  </div>
                  <h4 className="text-sm font-semibold text-white">{item.event_name}</h4>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => openEditModal(item)}
                    className="flex items-center gap-1 px-3 py-1.5 bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 rounded-xl text-xs font-semibold transition-all"
                  >
                    <Plus size={13} />
                    Add Date
                  </button>
                  <button
                    onClick={() => handleToggleHide(item)}
                    className={`p-1.5 rounded-xl border transition-colors ${
                      item.is_hidden
                        ? 'bg-slate-800 text-slate-400 border-white/10 hover:text-white'
                        : 'bg-white/5 text-slate-400 border-white/10 hover:text-red-400'
                    }`}
                    title={item.is_hidden ? 'Unhide' : 'Hide from list'}
                  >
                    {item.is_hidden ? <Eye size={15} /> : <EyeOff size={15} />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Section 2: Active Dated Events ───────────────────────────────── */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
          <CalendarDays size={16} className="text-emerald-400" />
          Active Dated Events ({filteredDated.length})
        </h3>

        {loading ? (
          <div className="text-center py-12 text-slate-500 text-sm">Loading events...</div>
        ) : filteredDated.length === 0 ? (
          <div className="bg-black/30 border border-white/10 rounded-2xl p-8 text-center text-slate-400 text-sm">
            No dated events found. Click <strong>Add Event</strong> or <strong>Scrape Website</strong> to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {filteredDated.map(item => (
              <div
                key={item.id}
                className={`bg-black/40 border rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors ${
                  item.is_hidden ? 'border-white/5 opacity-60' : 'border-white/10 hover:border-white/20'
                }`}
              >
                <div className="space-y-1 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${TYPE_BADGES[item.event_type] || TYPE_BADGES.Notice}`}>
                      {item.event_type}
                    </span>
                    <span className="text-emerald-400 font-mono text-xs font-semibold bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md">
                      {item.event_date}
                    </span>
                    {item.is_manual ? (
                      <span className="bg-purple-500/15 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded-full text-[10px] font-bold">
                        Manual
                      </span>
                    ) : (
                      <span className="bg-blue-500/10 text-blue-300 border border-blue-500/20 px-2 py-0.5 rounded-full text-[10px]">
                        Scraped
                      </span>
                    )}
                    {item.is_hidden && (
                      <span className="bg-red-500/15 text-red-400 border border-red-500/30 px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1">
                        <EyeOff size={10} /> Hidden
                      </span>
                    )}
                  </div>
                  <h4 className="text-sm font-semibold text-white">{item.event_name}</h4>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                    {item.semester && <span>Semester: {item.semester}</span>}
                    {item.department && <span>Dept: {item.department}</span>}
                    {item.source_url && item.source_url !== 'manual' && (
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-emerald-400/80 hover:text-emerald-300 flex items-center gap-1"
                      >
                        <ExternalLink size={11} /> Source
                      </a>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => openEditModal(item)}
                    className="p-1.5 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl border border-white/10 transition-colors"
                    title="Edit event"
                  >
                    <Edit2 size={14} />
                  </button>
                  <button
                    onClick={() => handleToggleHide(item)}
                    className={`flex items-center gap-1 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all ${
                      item.is_hidden
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25'
                        : 'bg-white/5 text-slate-400 border-white/10 hover:text-red-400'
                    }`}
                  >
                    {item.is_hidden ? (
                      <>
                        <Eye size={13} /> Unhide
                      </>
                    ) : (
                      <>
                        <EyeOff size={13} /> Hide
                      </>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Modal: Add Manual Event ───────────────────────────────────────── */}
      <AnimatePresence>
        {showAddModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-slate-900 border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Plus size={18} className="text-emerald-400" /> Add Event Manually
                </h3>
                <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-white">
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleAddEvent} className="space-y-4">
                <div>
                  <label className="block text-slate-400 text-xs font-semibold mb-1">Event Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. End Semester Exam Submission"
                    value={addForm.event_name}
                    onChange={e => setAddForm({ ...addForm, event_name: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Type</label>
                    <select
                      value={addForm.event_type}
                      onChange={e => setAddForm({ ...addForm, event_type: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    >
                      {EVENT_TYPES.map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Date</label>
                    <input
                      type="date"
                      value={addForm.event_date}
                      onChange={e => setAddForm({ ...addForm, event_date: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Semester (optional)</label>
                    <input
                      type="text"
                      placeholder="e.g. Sem 4"
                      value={addForm.semester}
                      onChange={e => setAddForm({ ...addForm, semester: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Department (optional)</label>
                    <input
                      type="text"
                      placeholder="e.g. Computer"
                      value={addForm.department}
                      onChange={e => setAddForm({ ...addForm, department: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    className="px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={addLoading}
                    className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-xl text-sm disabled:opacity-50"
                  >
                    {addLoading ? 'Adding...' : 'Add Event'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── Modal: Scrape Website ────────────────────────────────────────── */}
      <AnimatePresence>
        {showScrapeModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-slate-900 border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Globe size={18} className="text-blue-400" /> Safe Website Scrape
                </h3>
                <button onClick={() => setShowScrapeModal(false)} className="text-slate-400 hover:text-white">
                  <X size={18} />
                </button>
              </div>

              <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-3 text-xs text-blue-300 mb-4 space-y-1">
                <p>• Scraper stays strictly on the target website domain.</p>
                <p>• Protected against SSRF and private IP addresses.</p>
                <p>• Scrape will skip duplicate rows and never overwrite manual events.</p>
              </div>

              <form onSubmit={handleTriggerScrape} className="space-y-4">
                <div>
                  <label className="block text-slate-400 text-xs font-semibold mb-1">College Website URL *</label>
                  <input
                    type="url"
                    required
                    placeholder="https://frcrce.ac.in"
                    value={scrapeForm.college_url}
                    onChange={e => setScrapeForm({ ...scrapeForm, college_url: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 text-xs font-semibold mb-1">College Display Name</label>
                  <input
                    type="text"
                    placeholder="e.g. Fr. CRCE"
                    value={scrapeForm.college_name}
                    onChange={e => setScrapeForm({ ...scrapeForm, college_name: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowScrapeModal(false)}
                    className="px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={scrapeLoading}
                    className="px-4 py-2 bg-blue-500 hover:bg-blue-400 text-black font-bold rounded-xl text-sm disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {scrapeLoading && <RefreshCw size={13} className="animate-spin" />}
                    {scrapeLoading ? 'Scraping...' : 'Start Scrape'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── Modal: Edit / Add Date ────────────────────────────────────────── */}
      <AnimatePresence>
        {editingEvent && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-slate-900 border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Edit2 size={18} className="text-emerald-400" />
                  {editingEvent.event_date ? 'Edit Event' : 'Assign Date to Event'}
                </h3>
                <button onClick={() => setEditingEvent(null)} className="text-slate-400 hover:text-white">
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleSaveEdit} className="space-y-4">
                <div>
                  <label className="block text-slate-400 text-xs font-semibold mb-1">Event Name</label>
                  <input
                    type="text"
                    required
                    value={editForm.event_name}
                    onChange={e => setEditForm({ ...editForm, event_name: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Type</label>
                    <select
                      value={editForm.event_type}
                      onChange={e => setEditForm({ ...editForm, event_type: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    >
                      {EVENT_TYPES.map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Event Date</label>
                    <input
                      type="date"
                      value={editForm.event_date}
                      onChange={e => setEditForm({ ...editForm, event_date: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Semester</label>
                    <input
                      type="text"
                      value={editForm.semester}
                      onChange={e => setEditForm({ ...editForm, semester: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 text-xs font-semibold mb-1">Department</label>
                    <input
                      type="text"
                      value={editForm.department}
                      onChange={e => setEditForm({ ...editForm, department: e.target.value })}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setEditingEvent(null)}
                    className="px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editLoading}
                    className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-xl text-sm disabled:opacity-50"
                  >
                    {editLoading ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
