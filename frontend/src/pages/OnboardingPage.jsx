import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { GraduationCap, School, MapPin, Building2, FileText, ArrowRight, CheckCircle2, AlertCircle } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../hooks/useAuth';
import { updateProfile } from '../api/auth';
import { FallingPattern } from '../components/ui/falling-pattern';
import JoinCard from '../components/common/JoinCard';

export default function OnboardingPage() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const [educationLevel, setEducationLevel] = useState(user?.education_level || 'college');
  const [gradeOrYear, setGradeOrYear] = useState(user?.grade_or_year || '');
  const [location, setLocation] = useState(user?.location || '');
  const [institutionNameText, setInstitutionNameText] = useState(user?.institution_name_text || '');
  const [department, setDepartment] = useState(user?.extra_info?.department || '');
  const [rollNumber, setRollNumber] = useState(user?.extra_info?.roll_number || '');
  const [note, setNote] = useState(user?.extra_info?.note || '');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const gradeOptions = ['Grade 8', 'Grade 9', 'Grade 10', 'Grade 11', 'Grade 12'];
  const collegeYearOptions = ['First Year (FE)', 'Second Year (SE)', 'Third Year (TE)', 'Fourth Year (BE/BTech)', 'Postgraduate'];

  async function handleSubmit(e) {
    e.preventDefault();
    if (!gradeOrYear.trim()) {
      setError('Please select or specify your current grade or year');
      return;
    }

    setError('');
    setLoading(true);

    try {
      const payload = {
        education_level: educationLevel,
        grade_or_year: gradeOrYear.trim(),
        location: location.trim() || null,
        institution_name_text: institutionNameText.trim() || null,
        extra_info: {
          department: department.trim() || undefined,
          roll_number: rollNumber.trim() || undefined,
          note: note.trim() || undefined,
        },
      };

      await updateProfile(payload);
      toast.success('Profile setup complete!');
      await refreshUser();
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save profile. Please try again.');
      toast.error('Could not save profile');
    } finally {
      setLoading(false);
    }
  }

  function handleSkip() {
    navigate('/dashboard');
  }

  return (
    <div className="min-h-screen py-12 px-4 relative bg-black flex flex-col justify-center">
      {/* Background */}
      <div className="fixed inset-0 pointer-events-none" style={{ zIndex: 0 }}>
        <FallingPattern backgroundColor="#000000" className="h-full" />
      </div>

      <div className="max-w-2xl mx-auto w-full relative z-10">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mb-4">
            <GraduationCap size={28} />
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Welcome to SAIS, {user?.full_name?.split(' ')[0] || user?.username || 'Student'}!
          </h1>
          <p className="text-sm text-slate-400 mt-2 max-w-md mx-auto">
            Let&apos;s personalize your academic schedule and courses. You can update these details anytime.
          </p>
        </div>

        {/* Join Code Card (Optional join option) */}
        <div className="mb-8">
          <JoinCard />
        </div>

        {/* Main Onboarding Form */}
        <div className="p-6 sm:p-8 rounded-2xl bg-slate-900/80 border border-white/10 backdrop-blur-xl shadow-2xl">
          <div className="flex items-center justify-between pb-4 mb-6 border-b border-white/10">
            <div>
              <h2 className="text-lg font-semibold text-white">Student Academic Profile</h2>
              <p className="text-xs text-slate-400">Basic details to organize your classes and tasks</p>
            </div>
            <button
              type="button"
              onClick={handleSkip}
              className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              Skip for now &rarr;
            </button>
          </div>

          {error && (
            <div className="mb-6 p-3 rounded-xl bg-red-500/10 border border-red-500/30 flex items-center gap-2 text-xs text-red-300">
              <AlertCircle size={15} className="flex-shrink-0 text-red-400" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* 1. Education Level Toggle */}
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-2">
                Education Level
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setEducationLevel('school');
                    setGradeOrYear('');
                  }}
                  className={`p-3.5 rounded-xl border flex items-center justify-center gap-2.5 text-sm font-medium transition-all ${
                    educationLevel === 'school'
                      ? 'bg-emerald-500/10 border-emerald-500 text-emerald-300 shadow-lg shadow-emerald-500/10'
                      : 'bg-black/40 border-white/10 text-slate-400 hover:border-white/20'
                  }`}
                >
                  <School size={18} />
                  <span>School</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setEducationLevel('college');
                    setGradeOrYear('');
                  }}
                  className={`p-3.5 rounded-xl border flex items-center justify-center gap-2.5 text-sm font-medium transition-all ${
                    educationLevel === 'college'
                      ? 'bg-emerald-500/10 border-emerald-500 text-emerald-300 shadow-lg shadow-emerald-500/10'
                      : 'bg-black/40 border-white/10 text-slate-400 hover:border-white/20'
                  }`}
                >
                  <GraduationCap size={18} />
                  <span>College / University</span>
                </button>
              </div>
            </div>

            {/* 2. Grade or Year */}
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-2">
                {educationLevel === 'school' ? 'Current Grade / Class' : 'College Academic Year'} *
              </label>
              <div className="flex flex-wrap gap-2 mb-2">
                {(educationLevel === 'school' ? gradeOptions : collegeYearOptions).map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setGradeOrYear(opt)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      gradeOrYear === opt
                        ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300'
                        : 'bg-black/40 border-white/10 text-slate-400 hover:border-white/20'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={gradeOrYear}
                onChange={(e) => setGradeOrYear(e.target.value)}
                placeholder={educationLevel === 'school' ? 'Or type your grade (e.g. 10th)' : 'Or type your year (e.g. SE / 2nd Year)'}
                className="w-full px-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
              />
            </div>

            {/* 3. Institution Name & Location */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  School / College Name
                </label>
                <div className="relative">
                  <Building2 size={16} className="absolute left-3 top-3 text-slate-500" />
                  <input
                    type="text"
                    value={institutionNameText}
                    onChange={(e) => setInstitutionNameText(e.target.value)}
                    placeholder="e.g. St. Xavier's College"
                    className="w-full pl-9 pr-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  City / Location
                </label>
                <div className="relative">
                  <MapPin size={16} className="absolute left-3 top-3 text-slate-500" />
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="e.g. Mumbai, Maharashtra"
                    className="w-full pl-9 pr-4 py-2.5 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                  />
                </div>
              </div>
            </div>

            {/* 4. Optional Extra Info */}
            <div className="pt-2 border-t border-white/5 space-y-4">
              <p className="text-xs font-medium text-slate-400">Additional Details (Optional)</p>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Department / Stream
                  </label>
                  <input
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="e.g. Computer Engineering, Science"
                    className="w-full px-4 py-2 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Roll Number / Student ID
                  </label>
                  <input
                    type="text"
                    value={rollNumber}
                    onChange={(e) => setRollNumber(e.target.value)}
                    placeholder="e.g. 21CO14"
                    className="w-full px-4 py-2 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Note / Goals
                </label>
                <textarea
                  rows={2}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Any specific academic goals or schedule notes..."
                  className="w-full px-4 py-2 bg-black/40 border border-white/10 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-xs resize-none"
                />
              </div>
            </div>

            {/* Submit */}
            <div className="flex items-center gap-4 pt-2">
              <button
                type="submit"
                disabled={loading}
                className="flex-1 py-3 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-black border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    Save Profile & Go to Dashboard <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
