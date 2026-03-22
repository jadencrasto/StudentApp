import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { GraduationCap, Mail, Lock, User, UserCircle, ArrowRight, ArrowLeft } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../hooks/useAuth';
import { register, login } from '../api/auth';
import { FallingPattern } from '../components/ui/falling-pattern';

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { setToken } = useAuth();
  const navigate = useNavigate();

  const strength = useMemo(() => {
    if (!password) return 0;
    let s = 0;
    if (password.length >= 8) s++;
    if (/[A-Z]/.test(password)) s++;
    if (/[0-9]/.test(password) || /[^A-Za-z0-9]/.test(password)) s++;
    return s;
  }, [password]);

  const { strengthText, strengthColor } = useMemo(() => {
    switch (strength) {
      case 0: return { strengthText: '', strengthColor: 'bg-white/10' };
      case 1: return { strengthText: 'Weak', strengthColor: 'bg-red-500' };
      case 2: return { strengthText: 'Moderate', strengthColor: 'bg-emerald-400/50' };
      case 3: return { strengthText: 'Strong', strengthColor: 'bg-emerald-500' };
      default: return { strengthText: '', strengthColor: 'bg-white/10' };
    }
  }, [strength]);

  async function handleSubmit(e) {
    e.preventDefault();

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setError('');
    setLoading(true);

    try {
      const normalizedEmail = email.trim().toLowerCase();
      const normalizedUsername = username.trim();

      // 1. Register
      await register({
        email: normalizedEmail,
        username: normalizedUsername,
        full_name: fullName,
        password
      });

      // 2. Auto-login
      const { data } = await login({ email: normalizedEmail, password });
      setToken(data.access_token);

      toast.success('Account created!');
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed');
      toast.error(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 relative">
      {/* Falling pattern background */}
      <div className="fixed inset-0" style={{ zIndex: 0 }}>
        <FallingPattern
          backgroundColor="#000000"
          className="h-full"
        />
      </div>

      <div className="w-full max-w-md relative" style={{ zIndex: 1 }}>
        {/* Back Button */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
          className="absolute -top-10 left-0"
        >
          <Link 
            to="/" 
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-emerald-400 font-medium transition-colors"
          >
            <ArrowLeft size={16} /> Home
          </Link>
        </motion.div>

        {/* Logo/Title */}
        <div className="text-center mb-8">
          <motion.div
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.1 }}
            className="inline-flex w-14 h-14 bg-emerald-500 rounded-2xl items-center justify-center mb-4"
          >
            <GraduationCap size={28} className="text-black" />
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.25 }}
            className="font-display text-3xl text-white mb-1"
          >Join SAIS</motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.35 }}
            className="text-slate-400 text-sm"
          >Create your student account</motion.p>
        </div>

        {/* Register Card */}
        <motion.form
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          onSubmit={handleSubmit}
          className="bg-black/40 backdrop-blur-xl border border-white/10 p-8 pb-10 rounded-3xl shadow-2xl relative overflow-hidden flex flex-col gap-5"
        >
          {/* Full Name Input */}
          <motion.div
            initial={{ opacity: 0, x: -15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: 0.25 }}
          >
            <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Full Name (Optional)</label>
            <div className="relative">
              <UserCircle size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="John Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full pl-10 pr-4 py-3 bg-black/40 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/30 transition-all"
              />
            </div>
          </motion.div>

          {/* Username Input */}
          <motion.div
            initial={{ opacity: 0, x: -15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: 0.32 }}
          >
            <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="absolute bottom-0 left-0 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2" />
            <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Username</label>
            <div className="relative">
              <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="john_doe"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full pl-10 pr-4 py-3 bg-black/40 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/30 transition-all"
              />
            </div>
          </motion.div>

          {/* Email Input */}
          <motion.div
            initial={{ opacity: 0, x: -15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: 0.39 }}
          >
            <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Email</label>
            <div className="relative">
              <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="email"
                placeholder="you@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full pl-10 pr-4 py-3 bg-black/40 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/30 transition-all"
              />
            </div>
          </motion.div>

          {/* Password Input */}
          <motion.div
            initial={{ opacity: 0, x: -15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: 0.46 }}
          >
            <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Password</label>
            <div className="relative">
              <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full pl-10 pr-4 py-3 bg-black/40 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/30 transition-all"
              />
            </div>

            <AnimatePresence>
            {password && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.25 }}
                className="mt-2"
              >
                <div className="flex gap-1">
                  {[1, 2, 3].map(level => (
                    <motion.div
                      key={level}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.3, delay: level * 0.1 }}
                      style={{ transformOrigin: 'left' }}
                      className={`h-1 flex-1 rounded ${strength >= level ? strengthColor : 'bg-slate-700'}`}
                    />
                  ))}
                </div>
                <p className="text-xs text-slate-500 mt-1">{strengthText}</p>
              </motion.div>
            )}
            </AnimatePresence>
          </motion.div>

          {/* Error Display */}
          <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25 }}
              className="bg-red-400/10 border border-red-400/20 rounded-lg p-3"
            >
              <p className="text-red-400 text-sm">{error}</p>
            </motion.div>
          )}
          </AnimatePresence>

          {/* Submit Button */}
          <motion.button
            type="submit"
            disabled={loading}
            whileHover={{ scale: 1.02, boxShadow: '0 0 20px rgba(251,191,36,0.25)' }}
            whileTap={{ scale: 0.97 }}
            className="w-full py-3.5 px-4 bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-xl transition-all flex items-center justify-center gap-2 group disabled:opacity-70"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
            ) : (
              <>Create Account <ArrowRight size={16} /></>
            )}
          </motion.button>
        </motion.form>

        {/* Login Link */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.6 }}
          className="text-center text-sm text-slate-500 mt-6"
        >
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-emerald-400 hover:text-emerald-300 transition-colors">
            Sign In
          </Link>
        </motion.p>
      </div>
    </div>
  );
}
