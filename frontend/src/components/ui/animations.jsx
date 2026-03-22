import { motion, AnimatePresence } from 'framer-motion'

/* ── Shared easing curves ── */
const smooth = [0.4, 0, 0.2, 1]
const spring = { type: 'spring', stiffness: 300, damping: 30 }

/* ── Page wrapper — fades + slides every route ── */
export function PageTransition({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.35, ease: smooth }}
    >
      {children}
    </motion.div>
  )
}

/* ── Fade-in on scroll / mount ── */
export function FadeIn({ children, delay = 0, duration = 0.45, className = '', direction = 'up' }) {
  const dirs = {
    up:    { y: 14 },
    down:  { y: -14 },
    left:  { x: 14 },
    right: { x: -14 },
    none:  {},
  }
  return (
    <motion.div
      initial={{ opacity: 0, ...dirs[direction] }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration, delay, ease: smooth }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── Stagger container — children animate in sequence ── */
export function StaggerContainer({ children, stagger = 0.06, delay = 0, className = '' }) {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: {
          transition: { staggerChildren: stagger, delayChildren: delay },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── Individual stagger child ── */
export function StaggerItem({ children, className = '' }) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 12 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: smooth } },
      }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── Scale-in for cards / modals ── */
export function ScaleIn({ children, delay = 0, className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.35, delay, ease: smooth }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── AnimatePresence wrapper for conditional content ── */
export function AnimatedPresence({ children, mode = 'wait' }) {
  return <AnimatePresence mode={mode}>{children}</AnimatePresence>
}

/* ── List item with layout animation ── */
export function AnimatedListItem({ children, className = '', layoutId }) {
  return (
    <motion.div
      layout
      layoutId={layoutId}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -12, transition: { duration: 0.2 } }}
      transition={{ duration: 0.3, ease: smooth }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── Hover card — lifts subtly on hover ── */
export function HoverCard({ children, className = '', as = 'div' }) {
  const Comp = motion[as] || motion.div
  return (
    <Comp
      whileHover={{ y: -2, transition: { duration: 0.2, ease: smooth } }}
      whileTap={{ scale: 0.98 }}
      className={className}
    >
      {children}
    </Comp>
  )
}

/* ── Number counter animation ── */
export function CountUp({ value, className = '' }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: smooth }}
      className={className}
    >
      {value}
    </motion.span>
  )
}

/* ── Skeleton placeholder ── */
export function Skeleton({ className = '', lines = 1 }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`skeleton h-4 ${i === lines - 1 && lines > 1 ? 'w-3/4' : 'w-full'} ${className}`}
        />
      ))}
    </div>
  )
}

/* ── Card skeleton ── */
export function CardSkeleton({ className = '' }) {
  return (
    <div className={`bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 ${className}`}>
      <div className="skeleton h-4 w-1/3" />
      <div className="skeleton h-3 w-full" />
      <div className="skeleton h-3 w-2/3" />
    </div>
  )
}

/* ── Stat card skeleton ── */
export function StatSkeleton() {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="skeleton h-3 w-20" />
        <div className="skeleton h-8 w-8 rounded-lg" />
      </div>
      <div className="skeleton h-7 w-14 mb-1" />
      <div className="skeleton h-3 w-24" />
    </div>
  )
}

/* ── Progress bar with animation ── */
export function AnimatedProgress({ value, className = '', color = 'bg-emerald-400' }) {
  return (
    <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
      <motion.div
        className={`h-full rounded-full ${color}`}
        initial={{ width: 0 }}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.8, delay: 0.2, ease: smooth }}
      />
    </div>
  )
}
