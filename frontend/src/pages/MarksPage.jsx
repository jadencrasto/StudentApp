import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Award, Search, Filter, Calendar, BookOpen, CheckCircle2,
  AlertCircle, Clock, ShieldCheck, GraduationCap, ChevronRight
} from 'lucide-react';
import { classMarksAPI } from '../api/client';

export default function MarksPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [selectedSubject, setSelectedSubject] = useState('All');

  useEffect(() => {
    loadStudentMarks();
  }, []);

  async function loadStudentMarks() {
    setLoading(true);
    setError('');
    try {
      const res = await classMarksAPI.getStudentMarks();
      setData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load class marks');
    } finally {
      setLoading(false);
    }
  }

  // Extract distinct subjects for filter
  const subjects = useMemo(() => {
    if (!data?.exams) return ['All'];
    const set = new Set(data.exams.map((e) => e.subject));
    return ['All', ...Array.from(set)];
  }, [data]);

  // Filter exams by search and subject
  const filteredExams = useMemo(() => {
    if (!data?.exams) return [];
    return data.exams.filter((ex) => {
      const matchesSearch =
        ex.exam_title.toLowerCase().includes(search.toLowerCase()) ||
        ex.subject.toLowerCase().includes(search.toLowerCase()) ||
        ex.exam_type.toLowerCase().includes(search.toLowerCase());
      const matchesSubject = selectedSubject === 'All' || ex.subject === selectedSubject;
      return matchesSearch && matchesSubject;
    });
  }, [data, search, selectedSubject]);

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-6xl mx-auto flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs text-slate-500">Loading your marks...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 md:p-10 max-w-6xl mx-auto">
        <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm flex items-center gap-3">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  // Not enrolled in a class cohort (Independent Student view)
  if (!data?.enrolled) {
    return (
      <div className="p-6 md:p-10 max-w-4xl mx-auto">
        <div className="text-center py-16 px-6 bg-slate-900/40 border border-white/5 rounded-3xl backdrop-blur-sm">
          <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mx-auto mb-4">
            <GraduationCap size={32} />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Class Marks</h2>
          <p className="text-sm text-slate-400 max-w-md mx-auto mb-6 leading-relaxed">
            You are currently browsing as an independent student. Class marks are published directly by your school or college administration.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-slate-300">
            <ShieldCheck size={14} className="text-emerald-400" />
            Enrolled in a class? Join using your class code in the onboarding tab.
          </div>
        </div>
      </div>
    );
  }

  const { cohort, summary } = data;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* Page Header & Enrolled Class Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60 border border-white/10 p-5 rounded-2xl backdrop-blur-sm">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold text-white tracking-tight">Class Marks</h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
              {cohort?.name}
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono text-slate-400 bg-white/5">
              {cohort?.academic_year}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Official grades and exam scores published by your class administration.
          </p>
        </div>

        {/* Overall Percentage Badge */}
        {summary?.overall_percentage !== null && summary?.overall_percentage !== undefined && (
          <div className="flex items-center gap-3 bg-black/40 border border-white/10 px-4 py-2.5 rounded-xl self-start md:self-auto">
            <Award className="text-emerald-400" size={20} />
            <div>
              <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Overall Average</p>
              <p className={`text-base font-bold font-mono ${
                summary.overall_percentage >= 75
                  ? 'text-emerald-400'
                  : summary.overall_percentage >= 50
                  ? 'text-amber-400'
                  : 'text-rose-400'
              }`}>
                {summary.overall_percentage}%
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-900/40 border border-white/10 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <BookOpen size={20} />
          </div>
          <div>
            <p className="text-xs text-slate-400 font-medium">Published Exams</p>
            <p className="text-xl font-bold text-white font-mono mt-0.5">{summary?.total_exams || 0}</p>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-white/10 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle2 size={20} />
          </div>
          <div>
            <p className="text-xs text-slate-400 font-medium">Graded Tests</p>
            <p className="text-xl font-bold text-emerald-400 font-mono mt-0.5">{summary?.completed_exams || 0}</p>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-white/10 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <Clock size={20} />
          </div>
          <div>
            <p className="text-xs text-slate-400 font-medium">Pending Entry</p>
            <p className="text-xl font-bold text-amber-400 font-mono mt-0.5">
              {Math.max(0, (summary?.total_exams || 0) - (summary?.completed_exams || 0))}
            </p>
          </div>
        </div>
      </div>

      {/* Filters & Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search by subject or exam..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-black/40 border border-white/10 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          <Filter size={14} className="text-slate-500 flex-shrink-0" />
          {subjects.map((sub) => (
            <button
              key={sub}
              onClick={() => setSelectedSubject(sub)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                selectedSubject === sub
                  ? 'bg-emerald-500 text-black shadow-lg shadow-emerald-500/20'
                  : 'bg-white/5 text-slate-400 hover:text-white border border-white/5'
              }`}
            >
              {sub}
            </button>
          ))}
        </div>
      </div>

      {/* Exam Cards Grid */}
      {filteredExams.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-slate-900/40 border border-white/5">
          <Award size={32} className="mx-auto text-slate-600 mb-2" />
          <p className="text-slate-300 font-medium text-sm">No exam marks to display</p>
          <p className="text-xs text-slate-500 mt-1">Exams will appear here once published by your teacher.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredExams.map((ex) => (
            <motion.div
              key={ex.exam_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-slate-900/50 border border-white/10 hover:border-emerald-500/30 rounded-2xl p-5 flex flex-col justify-between transition-all backdrop-blur-sm"
            >
              <div className="space-y-3">
                {/* Header: Subject & Type */}
                <div className="flex items-start justify-between gap-2">
                  <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
                    {ex.subject}
                  </span>
                  <span className="text-[11px] font-mono text-slate-400 bg-white/5 px-2 py-0.5 rounded">
                    {ex.exam_type}
                  </span>
                </div>

                {/* Title */}
                <h3 className="text-white font-bold text-base leading-snug">{ex.exam_title}</h3>

                {/* Date */}
                {ex.exam_date && (
                  <p className="text-xs text-slate-500 flex items-center gap-1.5">
                    <Calendar size={12} className="text-slate-400" />
                    {ex.exam_date}
                  </p>
                )}
              </div>

              {/* Bottom Result Badge */}
              <div className="mt-6 pt-4 border-t border-white/5 flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Score</p>
                  <p className="text-sm font-bold text-white font-mono mt-0.5">
                    {ex.status === 'graded' ? (
                      <span>{ex.marks_obtained} <span className="text-slate-500 font-normal">/ {ex.max_marks}</span></span>
                    ) : ex.status === 'absent' ? (
                      <span className="text-rose-400 font-semibold">Absent</span>
                    ) : (
                      <span className="text-slate-400 italic font-normal">Not entered yet</span>
                    )}
                  </p>
                </div>

                <div>
                  {ex.status === 'graded' && ex.percentage !== null && (
                    <span className={`px-2.5 py-1 rounded-full text-xs font-bold font-mono border ${
                      ex.percentage >= 75
                        ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                        : ex.percentage >= 50
                        ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                        : 'text-rose-400 bg-rose-500/20 border-rose-500/30'
                    }`}>
                      {ex.percentage}%
                    </span>
                  )}
                  {ex.status === 'absent' && (
                    <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                      Absent
                    </span>
                  )}
                  {ex.status === 'not_entered' && (
                    <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-white/5 text-slate-400 border border-white/10">
                      Pending
                    </span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
