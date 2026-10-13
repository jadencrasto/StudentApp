import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../../hooks/useAuth'
import { FallingPattern } from '../ui/falling-pattern'
import { useClassNotifications } from '../../hooks/useClassNotifications'
import {
  LayoutDashboard, BookOpen, CalendarCheck, Trophy,
  Upload, LogOut, GraduationCap, Grid3X3, Newspaper, School, MessageSquare, FileText, Menu, X
} from 'lucide-react'

const NAV = [
  { to: '/dashboard',              icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/dashboard/assignments',  icon: BookOpen,         label: 'Assignments' },
  { to: '/dashboard/attendance',   icon: CalendarCheck,    label: 'Attendance' },
  { to: '/dashboard/activities',   icon: Trophy,           label: 'Activities' },
  { to: '/dashboard/timetable',    icon: Grid3X3,          label: 'Timetable' },
  { to: '/dashboard/events',       icon: Newspaper,        label: 'College Events' },
  { to: '/dashboard/classroom',    icon: School,           label: 'Classroom' },
  { to: '/dashboard/classroom/materials', icon: FileText,  label: 'Course Materials' },
  { to: '/dashboard/documents',    icon: Upload,           label: 'Upload Doc' },
  { to: '/dashboard/chat',         icon: MessageSquare,    label: 'AI Chatbot' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Start background checks for native browser notifications
  useClassNotifications()

  function closeMobile() { setMobileOpen(false) }

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="px-6 py-5 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <motion.div
            whileHover={{ rotate: [0, -8, 8, 0], transition: { duration: 0.5 } }}
            className="w-9 h-9 bg-emerald-500 rounded-lg flex items-center justify-center flex-shrink-0"
          >
            <GraduationCap size={20} className="text-black" />
          </motion.div>
          <div>
            <p className="font-display text-lg leading-none text-white">SAIS</p>
            <p className="text-xs text-gray-500 mt-0.5">Academic Intelligence</p>
          </div>
        </div>
        {/* Close button — mobile only */}
        <button
          onClick={closeMobile}
          className="md:hidden p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          aria-label="Close menu"
        >
          <X size={20} />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map(({ to, icon: Icon, label }) => (
          <div key={to}>
            <NavLink
              to={to}
              end={to === '/dashboard'}
              onClick={closeMobile}
              className={({ isActive }) =>
                `relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 min-h-[44px] ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-400'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-white/5'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.div
                      layoutId="nav-active"
                      className="absolute inset-0 bg-emerald-500/10 border border-emerald-500/20 rounded-lg"
                      transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-3">
                    <Icon size={17} />
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          </div>
        ))}
      </nav>

      {/* User */}
      <div className="px-4 py-4 border-t border-white/10">
        <div className="flex items-center gap-3 mb-3">
          <motion.div
            whileHover={{ scale: 1.08 }}
            transition={{ type: 'spring', stiffness: 400, damping: 17 }}
            className="w-8 h-8 bg-emerald-500 rounded-full flex items-center justify-center text-black font-semibold text-sm flex-shrink-0"
          >
            {user?.username?.[0]?.toUpperCase() || 'U'}
          </motion.div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-white truncate">{user?.username}</p>
            <p className="text-xs text-gray-500 truncate">{user?.email}</p>
          </div>
        </div>
        <motion.button
          whileHover={{ x: 2 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => { closeMobile(); logout() }}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-red-400/10 transition-colors duration-200 min-h-[44px]"
        >
          <LogOut size={15} />
          Sign out
        </motion.button>
      </div>
    </>
  )

  return (
    <div className="flex min-h-screen bg-black">
      {/* ── Mobile hamburger button ── */}
      <button
        onClick={() => setMobileOpen(true)}
        className="md:hidden fixed top-4 left-4 z-50 p-2.5 min-w-[44px] min-h-[44px] bg-emerald-500 hover:bg-emerald-600 rounded-lg shadow-lg shadow-emerald-500/20 flex items-center justify-center transition-colors"
        aria-label="Open menu"
      >
        <Menu size={20} className="text-black" />
      </button>

      {/* ── Mobile overlay ── */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={closeMobile}
            className="md:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          />
        )}
      </AnimatePresence>

      {/* ── Sidebar ── */}
      {/* Mobile: off-canvas slide-in; Desktop: fixed sidebar */}
      <aside
        className={`
          fixed top-0 left-0 h-full w-64 flex flex-col z-50
          transform transition-transform duration-300 ease-in-out
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 md:z-10
          border-r border-white/10
        `}
        style={{ background: 'rgba(0,0,0,0.92)', backdropFilter: 'blur(12px)' }}
      >
        {sidebarContent}
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 md:ml-64 min-h-screen relative">
        {/* Falling pattern background */}
        <div className="fixed inset-0 md:left-64 pointer-events-none" style={{ zIndex: 0 }}>
          <FallingPattern
            backgroundColor="#000000"
            duration={180}
            className="h-full"
            style={{ maskImage: 'radial-gradient(ellipse at center, transparent 5%, #000000 90%)' }}
          />
        </div>
        <div className="relative" style={{ zIndex: 1 }}>
          {/* Top padding on mobile to clear the hamburger button */}
          <div className="pt-16 md:pt-0">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  )
}
