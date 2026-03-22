import { useNavigate } from 'react-router-dom';
import { FallingPattern } from '../components/ui/falling-pattern';
import {
  GraduationCap,
  Calendar,
  BarChart3,
  Brain,
  Bell,
  MessageSquare,
  BookOpen,
  Clock,
  TrendingUp,
  Shield,
  Zap,
  Activity,
  CheckCircle2,
  ArrowRight,
  Github
} from 'lucide-react';

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-black text-white font-sans" style={{ colorScheme: 'dark' }}>
      <style>{`
        .landing-selection::selection { background: rgba(16,185,129,0.3); }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }
        .float-anim { animation: float 6s ease-in-out infinite; }
      `}</style>

      {/* Falling Pattern Background */}
      <div className="fixed inset-0 pointer-events-none" style={{ zIndex: 0 }}>
        <FallingPattern backgroundColor="#000000" />
      </div>

      {/* Navigation */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 50,
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
      }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px', height: '64px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ width: '36px', height: '36px', background: '#10B981', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <GraduationCap size={22} style={{ color: '#000' }} />
            </div>
            <span style={{ fontWeight: 800, fontSize: '20px', letterSpacing: '-0.5px' }}>SAIS</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '32px', fontSize: '14px', fontWeight: 500, color: '#9CA3AF' }}>
            <a href="#features" style={{ textDecoration: 'none', color: 'inherit', transition: 'color 0.2s' }}
               onMouseEnter={e => e.target.style.color = '#fff'}
               onMouseLeave={e => e.target.style.color = '#9CA3AF'}>Features</a>
            <a href="#modules" style={{ textDecoration: 'none', color: 'inherit', transition: 'color 0.2s' }}
               onMouseEnter={e => e.target.style.color = '#fff'}
               onMouseLeave={e => e.target.style.color = '#9CA3AF'}>Modules</a>
            <a href="#benefits" style={{ textDecoration: 'none', color: 'inherit', transition: 'color 0.2s' }}
               onMouseEnter={e => e.target.style.color = '#fff'}
               onMouseLeave={e => e.target.style.color = '#9CA3AF'}>Benefits</a>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              onClick={() => navigate('/login')}
              style={{
                background: '#fff', color: '#000', border: 'none', padding: '8px 18px',
                borderRadius: '8px', fontSize: '14px', fontWeight: 700, cursor: 'pointer',
                transition: 'background 0.2s'
              }}
              onMouseEnter={e => e.target.style.background = '#e5e7eb'}
              onMouseLeave={e => e.target.style.background = '#fff'}
            >
              Sign In
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section style={{ position: 'relative', paddingTop: '140px', paddingBottom: '120px', overflow: 'hidden' }}>
        {/* Background layers */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, rgba(6,78,59,0.4) 0%, #000 50%, #000 100%)' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 50%, rgba(16,185,129,0.15) 0%, transparent 60%)' }} />
        {/* Dot pattern */}
        <div style={{
          position: 'absolute', inset: 0, opacity: 0.15,
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '30px 30px'
        }} />

        <div style={{ position: 'relative', zIndex: 10, maxWidth: '1280px', margin: '0 auto', padding: '0 24px', textAlign: 'center' }}>
          {/* Badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '8px',
            background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)',
            borderRadius: '999px', padding: '6px 16px', fontSize: '13px', fontWeight: 600,
            color: '#34D399', marginBottom: '28px'
          }}>
            <Activity size={14} />
            Smart Academic Intelligence System
          </div>

          <h1 style={{ fontSize: 'clamp(40px, 7vw, 80px)', fontWeight: 900, letterSpacing: '-2px', lineHeight: 1.05, marginBottom: '24px' }}>
            Predict Academic<br />
            <span style={{ color: '#34D399' }}>Risk Before It Happens</span>
          </h1>

          <p style={{ fontSize: '18px', color: '#9CA3AF', maxWidth: '640px', margin: '0 auto 40px', lineHeight: 1.7 }}>
            AI-augmented academic planning for students and institutions. Track assignments, attendance, classroom sync, timetable health, and event-driven risk alerts — all in one place.
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '16px' }}>
            <button
              onClick={() => navigate('/register')}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                background: '#10B981', color: '#000', border: 'none',
                padding: '14px 32px', borderRadius: '10px', fontWeight: 800,
                fontSize: '16px', cursor: 'pointer',
                boxShadow: '0 0 30px rgba(16,185,129,0.35)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => { e.currentTarget.style.background = '#059669'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = '#10B981'; e.currentTarget.style.transform = 'translateY(0)'; }}
            >
              Start Tracking <ArrowRight size={18} />
            </button>
            <button
              onClick={() => navigate('/login')}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                background: 'rgba(255,255,255,0.05)', color: '#fff',
                border: '1px solid rgba(255,255,255,0.12)',
                padding: '14px 32px', borderRadius: '10px', fontWeight: 700,
                fontSize: '16px', cursor: 'pointer', transition: 'all 0.2s'
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.transform = 'translateY(0)'; }}
            >
              Sign In
            </button>
          </div>

          {/* Stats row */}
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '40px', marginTop: '64px' }}>
            {[
              { value: '6+', label: 'Core Modules' },
              { value: 'AI', label: 'Risk Engine' },
              { value: 'Real-time', label: 'Alerts' },
              { value: '1-Click', label: 'Google Sync' },
            ].map((stat, i) => (
              <div key={i} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '28px', fontWeight: 900, color: '#10B981' }}>{stat.value}</div>
                <div style={{ fontSize: '13px', color: '#6B7280', marginTop: '4px' }}>{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom fade */}
        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '100px', background: 'linear-gradient(to top, #000, transparent)', zIndex: 10 }} />
      </section>

      {/* Features Section */}
      <section id="features" style={{ padding: '96px 0', background: '#000', position: 'relative', zIndex: 20 }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px' }}>
          <div style={{ textAlign: 'center', marginBottom: '60px' }}>
            <h2 style={{ fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 800, marginBottom: '16px', letterSpacing: '-1px' }}>
              Platform Capabilities
            </h2>
            <p style={{ color: '#9CA3AF', maxWidth: '560px', margin: '0 auto', lineHeight: 1.6 }}>
              Built for students, educators, and academic teams who want to detect workload and performance risks before they escalate.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[
              { icon: BookOpen, title: 'Assignment Intelligence', description: 'Extract tasks, deadlines, question counts, and effort estimates from uploaded PDFs, images, or documents.', color: '#10B981' },
              { icon: Shield, title: 'Attendance Risk Engine', description: 'Monitor subject-wise attendance in real time with threshold alerts and recovery planning insights.', color: '#34D399' },
              { icon: Activity, title: 'Classroom Sync', description: 'Connect Google Classroom to sync courses, assignments, posting timelines, and submission statuses.', color: '#6EE7B7' },
              { icon: Calendar, title: 'Academic Event Ingestion', description: 'Pull college notices, exam schedules, holiday calendars, and institutional announcements into one timeline.', color: '#10B981' },
              { icon: Bell, title: 'Smart Alerts', description: 'Detect deadline clustering, missed-submission risk, attendance drop, and scheduling conflicts automatically.', color: '#34D399' },
              { icon: TrendingUp, title: 'Unified Dashboard', description: 'See assignments, attendance, alerts, activities, and academic calendar signals in one operational view.', color: '#6EE7B7' },
            ].map((feature, i) => (
              <FeatureCard key={i} {...feature} />
            ))}
          </div>
        </div>
      </section>

      {/* Core Modules Section */}
      <section id="modules" style={{ padding: '96px 0', background: '#09090b', position: 'relative' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '100px', background: 'linear-gradient(to bottom, #000, transparent)', pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '100px', background: 'linear-gradient(to top, #000, transparent)', pointerEvents: 'none' }} />

        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px' }}>
          <div style={{ textAlign: 'center', marginBottom: '60px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '12px' }}>
              <Brain size={30} style={{ color: '#34D399' }} />
              <h2 style={{ fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 800, letterSpacing: '-1px' }}>Core Modules</h2>
            </div>
            <p style={{ color: '#9CA3AF', maxWidth: '560px', margin: '0 auto' }}>
              Each module is purpose-built to track a specific dimension of your academic life.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-6xl mx-auto">
            {/* Left Col */}
            <div className="flex flex-col gap-5">
              <BentoCard 
                title="Classroom Connector" 
                description="Integrates with Google Classroom and keeps course and assignment data aligned." 
                image="https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=600&auto=format&fit=crop&q=80" 
                className="h-[300px]" 
              />
              <BentoCard 
                title="Document Analyzer" 
                description="OCR + NLP extraction for assignment metadata, due dates, and workload context." 
                image="https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=600&auto=format&fit=crop&q=80" 
                className="h-[240px]" 
              />
            </div>
            {/* Middle Col */}
            <div className="flex flex-col gap-5">
              <BentoCard 
                title="Attendance Monitor" 
                description="Tracks attendance health by subject and surfaces low-threshold risk patterns." 
                image="https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=600&auto=format&fit=crop&q=80" 
                className="h-[560px] md:h-full" 
              />
            </div>
            {/* Right Col */}
            <div className="flex flex-col gap-5">
              <BentoCard 
                title="Activity Planner" 
                description="Captures non-academic activities and flags deadline/event collisions." 
                image="https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=600&auto=format&fit=crop&q=80" 
                className="h-[240px]" 
              />
              <BentoCard 
                title="Calendar Intelligence" 
                description="Merges assignment deadlines with college events for practical planning visibility." 
                image="https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=600&auto=format&fit=crop&q=80" 
                className="h-[300px]" 
              />
            </div>
          </div>
        </div>
      </section>

      {/* Unified Risk Architecture */}
      <section id="architecture" className="py-24 bg-black relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <div className="inline-flex items-center justify-center px-4 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-medium mb-6">
              <div className="w-2 h-2 rounded-full bg-emerald-500 mr-2 animate-pulse" />
              Unified Intelligence
            </div>
            <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-6">Unified Risk Engine</h2>
            <p className="text-gray-400 max-w-2xl mx-auto text-[17px] leading-relaxed">
              All academic signals, attendance data, and document inferences flow into a unified risk analysis layer &mdash; keeping every alert contextually aware.
            </p>
          </div>

          <div className="relative max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-12 md:gap-4 my-20">
            {/* Left Column */}
            <div className="flex flex-col gap-12 w-full md:w-72 relative z-10">
              <BridgeBox title="Assignments" tag="Extracted" desc="Workloads, due dates, and NLP-analyzed complexities." />
              <BridgeBox title="Attendance" tag="Real-time" desc="Daily presence logs mapped against threshold rules." />
            </div>

            {/* Center Flow Diagram */}
            <div className="flex-1 flex flex-col items-center relative z-0 min-h-[400px] justify-center w-full px-4 md:px-0">
              {/* Top signal lines */}
              <div className="flex flex-wrap items-center justify-center gap-4 md:gap-8 mb-12 w-full">
                {['Classroom', 'Uploads', 'ERP Sync', 'Manual'].map((src, i) => (
                  <div key={i} className="px-4 py-2 rounded-full border border-white/10 text-white text-[11px] font-mono tracking-wider bg-[#050505] z-10 flex items-center gap-2">
                    <div className="w-3 h-3 rounded-sm border border-emerald-500/30 flex items-center justify-center"><div className="w-1 h-1 bg-emerald-500" /></div>
                    {src}
                  </div>
                ))}
              </div>
              
              {/* Connecting lines SVG */}
              <svg className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-[300px] pointer-events-none opacity-20 hidden md:block" preserveAspectRatio="none">
                <path d="M 0 50 Q 250 50 250 150 T 500 150" fill="none" stroke="#10B981" strokeWidth="2" />
                <path d="M 0 250 Q 250 250 250 150 T 500 150" fill="none" stroke="#10B981" strokeWidth="2" />
                <path d="M 500 50 Q 250 50 250 150 T 0 150" fill="none" stroke="#10B981" strokeWidth="2" />
                <path d="M 500 250 Q 250 250 250 150 T 0 150" fill="none" stroke="#10B981" strokeWidth="2" />
              </svg>

              <div className="relative z-20 w-full max-w-[320px]">
                <div className="bg-[#050505] border border-white/10 rounded-3xl p-8 shadow-2xl shadow-emerald-500/10 flex flex-col items-center text-center w-full relative">
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-semibold tracking-wider font-mono uppercase">
                    <Shield size={12} /> RISK ENGINE LAYER
                  </div>
                  
                  <div className="w-full h-32 mt-6 relative overflow-hidden flex items-end justify-center rounded-2xl bg-gradient-to-t from-emerald-500/10 to-transparent border border-emerald-500/20">
                    {/* Concentric arcs */}
                    <div className="absolute bottom-0 w-[150%] h-[150%] rounded-[100%] border-[2px] border-emerald-500/20 translate-y-1/2" />
                    <div className="absolute bottom-0 w-[100%] h-[100%] rounded-[100%] border-[2px] border-emerald-500/40 translate-y-1/2" />
                    <div className="absolute bottom-0 w-[50%] h-[50%] rounded-[100%] bg-emerald-500 blur-[30px] translate-y-1/2 opacity-30" />
                    
                    <span className="relative z-10 text-white font-bold mb-4 tracking-widest uppercase text-sm">Engine</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column */}
            <div className="flex flex-col gap-12 w-full md:w-72 relative z-10">
              <BridgeBox title="College Events" tag="Ingested" desc="Exam schedules, holidays, and campus events timeline." />
              <BridgeBox title="Smart Alerts" tag="Output" desc="Actionable early warnings for impending academic risk." />
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section style={{ padding: '120px 0', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(6,78,59,0.2)' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at center, rgba(16,185,129,0.15) 0%, transparent 65%)' }} />
        <div style={{
          position: 'absolute', inset: 0, opacity: 0.08,
          backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.2) 1px, transparent 1px)',
          backgroundSize: '28px 28px'
        }} />

        {/* Floating icon */}
        <div className="float-anim" style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', opacity: 0.06, pointerEvents: 'none' }}>
          <GraduationCap size={400} style={{ color: '#10B981' }} />
        </div>

        <div style={{ position: 'relative', zIndex: 10, maxWidth: '800px', margin: '0 auto', padding: '0 24px', textAlign: 'center' }}>
          <h2 style={{ fontSize: 'clamp(30px, 5vw, 52px)', fontWeight: 900, letterSpacing: '-1.5px', marginBottom: '20px', lineHeight: 1.1 }}>
            Ready to de-risk your<br />academic workflow?
          </h2>
          <p style={{ fontSize: '18px', color: '#D1D5DB', marginBottom: '40px', lineHeight: 1.6 }}>
            Connect your classroom, upload your documents, and generate actionable insights in minutes.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '16px' }}>
            <button
              onClick={() => navigate('/register')}
              style={{
                background: '#10B981', color: '#000', border: 'none',
                padding: '16px 40px', borderRadius: '10px', fontWeight: 800,
                fontSize: '17px', cursor: 'pointer',
                boxShadow: '0 0 40px rgba(16,185,129,0.35)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => { e.currentTarget.style.background = '#059669'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = '#10B981'; e.currentTarget.style.transform = 'translateY(0)'; }}
            >
              Launch SAIS
            </button>
            <button
              onClick={() => navigate('/login')}
              style={{
                background: 'rgba(255,255,255,0.08)', color: '#fff',
                border: '1px solid rgba(255,255,255,0.2)',
                padding: '16px 40px', borderRadius: '10px', fontWeight: 700,
                fontSize: '17px', cursor: 'pointer', transition: 'all 0.2s'
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.15)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.transform = 'translateY(0)'; }}
            >
              Sign In
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ position: 'relative', zIndex: 50, background: '#000', borderTop: '1px solid rgba(255,255,255,0.1)', padding: '48px 0' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={18} style={{ color: '#10B981' }} />
            <span style={{ fontWeight: 800, fontSize: '18px' }}>SAIS</span>
          </div>
          <p style={{ color: '#4B5563', fontSize: '13px' }}>
            © {new Date().getFullYear()} SAIS — Smart Academic Intelligence System
          </p>
          <div style={{ display: 'flex', gap: '20px' }}>
            {['GitHub', 'Docs', 'Support'].map(link => (
              <a key={link} href="#" style={{ color: '#4B5563', fontSize: '13px', textDecoration: 'none', transition: 'color 0.2s' }}
                 onMouseEnter={e => e.target.style.color = '#fff'}
                 onMouseLeave={e => e.target.style.color = '#4B5563'}>{link}</a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function FeatureCard({ icon: Icon, title, description }) {
  return (
    <div
      className="relative group rounded-2xl overflow-hidden border border-white/10 bg-[#030303] transition-all hover:border-emerald-500/30 flex flex-col items-center p-8 text-center"
    >
      {/* Grid Pattern Background */}
      <div 
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
          backgroundPosition: 'center'
        }}
      />
      {/* Glow on hover */}
      <div className="absolute inset-0 bg-emerald-500/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

      <div className="relative z-10 w-12 h-12 rounded-xl bg-[#000000] border border-emerald-500/20 flex items-center justify-center mb-6">
        <Icon size={20} className="text-emerald-400" />
      </div>
      <h3 className="relative z-10 text-[17px] font-bold text-white mb-4">{title}</h3>
      <p className="relative z-10 text-[14px] text-gray-400 leading-relaxed font-medium">{description}</p>
    </div>
  );
}

function BentoCard({ title, description, image, className }) {
  return (
    <div className={`group relative rounded-3xl border border-white/5 overflow-hidden bg-black ${className}`}>
      {/* Background Image */}
      <img 
        src={image} 
        alt={title} 
        className="absolute inset-0 w-full h-full object-cover opacity-30 group-hover:opacity-50 group-hover:scale-105 transition-all duration-700 ease-out" 
      />
      {/* Gradient Overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black via-[#000000]/80 to-transparent" />
      
      {/* Content */}
      <div className="absolute bottom-0 left-0 p-8 w-full z-10">
        <h3 className="text-xl font-bold text-white mb-3">{title}</h3>
        <p className="text-[14px] text-gray-300 leading-relaxed max-w-sm">{description}</p>
      </div>
    </div>
  );
}

function RiskCard({ icon: Icon, title, description }) {
  return (
    <div
      style={{
        borderRadius: '14px', border: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(255,255,255,0.02)', padding: '24px',
        transition: 'all 0.3s', cursor: 'default',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'rgba(248,113,113,0.3)';
        e.currentTarget.style.background = 'rgba(248,113,113,0.04)';
        e.currentTarget.style.transform = 'translateY(-4px)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)';
        e.currentTarget.style.background = 'rgba(255,255,255,0.02)';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <div style={{
        width: '48px', height: '48px', borderRadius: '12px',
        background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '16px'
      }}>
        <Icon size={24} style={{ color: '#F87171' }} />
      </div>
      <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#fff', marginBottom: '8px' }}>{title}</h3>
      <p style={{ color: '#9CA3AF', fontSize: '14px', lineHeight: 1.6 }}>{description}</p>
    </div>
  );
}

function BridgeBox({ title, desc, tag }) {
  return (
    <div className="bg-[#050505] border border-white/5 rounded-2xl p-6 transition-all hover:border-emerald-500/20 hover:bg-[#0a0a0a]">
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-white font-bold text-sm tracking-wide uppercase">{title}</h4>
        <div className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 text-[10px] font-mono font-bold tracking-widest">{tag}</div>
      </div>
      <p className="text-gray-400 text-xs leading-relaxed">{desc}</p>
    </div>
  );
}
