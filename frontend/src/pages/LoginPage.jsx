import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { GraduationCap, Mail, Lock, ArrowRight, ArrowLeft } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useAuth } from '../hooks/useAuth';
import { login } from '../api/auth';
import { FallingPattern } from '../components/ui/falling-pattern';

const ease = [0.4, 0, 0.2, 1];

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { setToken } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const { data } = await login({ email: email.trim().toLowerCase(), password });
      setToken(data.access_token);
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Please try again.');
      toast.error('Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative">
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
          transition={{ duration: 0.5, ease }}
          className="absolute -top-16 left-0"
        >
          <Link 
            to="/" 
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-emerald-400 font-medium transition-colors"
          >
            <ArrowLeft size={16} /> Home
          </Link>
        </motion.div>

        {/* Logo/Title */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease }}
          className="text-center mb-8"
        >
          <motion.div
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ duration: 0.6, delay: 0.1, type: 'spring', stiffness: 200 }}
            className="inline-flex w-14 h-14 bg-emerald-500 rounded-2xl items-center justify-center mb-4"
          >
            <GraduationCap size={28} className="text-black" />
          </motion.div>
          <motion.h1
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="font-display text-3xl text-white mb-1"
          >Welcome back</motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="text-slate-400 text-sm"
          >Sign in to your SAIS account</motion.p>
        </motion.div>

        {/* Login Card */}
        <motion.form
          initial={{ opacity: 0, y: 20, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.25, ease }}
          onSubmit={handleSubmit}
          className="bg-black/40 backdrop-blur-xl border border-white/10 p-8 pb-10 rounded-3xl shadow-2xl relative overflow-hidden flex flex-col gap-5"
        >
          {/* Email Input */}
          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.4 }}
          >
            <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="absolute bottom-0 left-0 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2" />
            <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">Email</label>
            <div className="relative">
              <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="email"
                placeholder="you@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full pl-10 pr-4 py-3 bg-black/40 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/50 transition-all duration-200"
              />
            </div>
          </motion.div>

          {/* Password Input */}
          <motion.div
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5, duration: 0.4 }}
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
                className="w-full pl-10 pr-4 py-3 bg-black/40 border border-white/10 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/50 transition-all duration-200"
              />
            </div>
          </motion.div>

          {/* Error Display */}
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="bg-red-400/10 border border-red-400/20 rounded-lg p-3"
            >
              <p className="text-red-400 text-sm">{error}</p>
            </motion.div>
          )}

          {/* Submit Button */}
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.4 }}
            whileHover={{ scale: 1.01, boxShadow: '0 0 24px rgba(251,191,36,0.2)' }}
            whileTap={{ scale: 0.97 }}
            type="submit"
            disabled={loading}
            className="w-full py-3.5 px-4 bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-xl transition-all flex items-center justify-center gap-2 group disabled:opacity-70"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
            ) : (
              <>Sign In <ArrowRight size={16} /></>
            )}
          </motion.button>
        </motion.form>

        {/* Register Link */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.7, duration: 0.5 }}
          className="text-center mt-8 text-gray-400 text-sm"
        >
          Don't have an account?{' '}
          <Link to="/register" className="text-sm font-medium text-emerald-400 hover:text-emerald-300 transition-colors">
            Create one
          </Link>
        </motion.p>
      </div>
    </div>
  );
}
