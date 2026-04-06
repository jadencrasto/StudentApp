import { lazy, Suspense, Component } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useAuth } from './hooks/useAuth'
import Layout from './components/layout/Layout'
import ProtectedRoute from './components/layout/ProtectedRoute'

// Direct imports for frequently-used pages (avoids lazy chunk-load failures on tab switch)
import DashboardPage from './pages/DashboardPage'
import AssignmentsPage from './pages/AssignmentsPage'
import AttendancePage from './pages/AttendancePage'
import ActivitiesPage from './pages/ActivitiesPage'
import TimetableSetupPage from './pages/TimetableSetupPage'
import LandingPage from './pages/LandingPage'

// Lazy-load less frequently visited pages
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const UploadPage = lazy(() => import('./pages/UploadPage'))
const CollegeEventsPage = lazy(() => import('./pages/events/CollegeEventsPage'))
const ClassroomDashboardPage = lazy(() => import('./pages/classroom/ClassroomDashboardPage'))
const CourseMaterialsPage = lazy(() => import('./pages/classroom/CourseMaterialsPage'))
const ChatBotPage = lazy(() => import('./pages/ChatBotPage'))

const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -4 },
  transition: { duration: 0.3, ease: [0.4, 0, 0.2, 1] },
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="flex flex-col items-center gap-3"
      >
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-slate-500">Loading…</span>
      </motion.div>
    </div>
  )
}

class ErrorBoundaryInner extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  componentDidUpdate(prevProps) {
    // Reset error state when the route changes
    if (prevProps.locationKey !== this.props.locationKey && this.state.hasError) {
      this.setState({ hasError: false })
    }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-64 gap-4">
          <p className="text-slate-400">Something went wrong loading this page.</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="px-4 py-2 bg-amber-400 text-slate-900 font-semibold rounded-xl text-sm"
          >
            Try Again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function ErrorBoundary({ children }) {
  const location = useLocation()
  return <ErrorBoundaryInner locationKey={location.key}>{children}</ErrorBoundaryInner>
}

export default function App() {
  const location = useLocation()
  return (
    <Suspense fallback={<PageLoader />}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          {/* Public: Landing Page */}
          <Route path="/" element={<LandingPage />} />

          {/* Public: Auth */}
          <Route path="/login" element={<motion.div {...pageTransition}><LoginPage /></motion.div>} />
          <Route path="/register" element={<motion.div {...pageTransition}><RegisterPage /></motion.div>} />

          {/* Protected: Dashboard & sub-pages (moved from "/" to "/dashboard") */}
          <Route path="/dashboard" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route index element={<ErrorBoundary><motion.div {...pageTransition} key="dashboard"><DashboardPage /></motion.div></ErrorBoundary>} />
            <Route path="assignments" element={<ErrorBoundary><motion.div {...pageTransition} key="assignments"><AssignmentsPage /></motion.div></ErrorBoundary>} />
            <Route path="attendance" element={<ErrorBoundary><motion.div {...pageTransition} key="attendance"><AttendancePage /></motion.div></ErrorBoundary>} />
            <Route path="activities" element={<ErrorBoundary><motion.div {...pageTransition} key="activities"><ActivitiesPage /></motion.div></ErrorBoundary>} />
            <Route path="timetable" element={<ErrorBoundary><motion.div {...pageTransition} key="timetable"><TimetableSetupPage /></motion.div></ErrorBoundary>} />
            <Route path="events" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><motion.div {...pageTransition} key="events"><CollegeEventsPage /></motion.div></Suspense></ErrorBoundary>} />
            <Route path="classroom" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><motion.div {...pageTransition} key="classroom"><ClassroomDashboardPage /></motion.div></Suspense></ErrorBoundary>} />
            <Route path="classroom/materials" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><motion.div {...pageTransition} key="classroom-materials"><CourseMaterialsPage /></motion.div></Suspense></ErrorBoundary>} />
            <Route path="documents" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><motion.div {...pageTransition} key="documents"><UploadPage /></motion.div></Suspense></ErrorBoundary>} />
            <Route path="upload" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><motion.div {...pageTransition} key="upload"><UploadPage /></motion.div></Suspense></ErrorBoundary>} />
            <Route path="chat" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><motion.div {...pageTransition} key="chat"><ChatBotPage /></motion.div></Suspense></ErrorBoundary>} />
          </Route>
        </Routes>
      </AnimatePresence>
    </Suspense>
  )
}
