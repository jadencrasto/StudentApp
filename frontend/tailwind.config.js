/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"DM Serif Display"', 'Georgia', 'serif'],
        body:    ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        ink:     { 50:'#f0f0ee', 100:'#d9d8d4', 900:'#1a1917' },
        emerald: {
          300: '#6EE7B7',
          400: '#34D399',
          500: '#10B981',
          600: '#059669',
          700: '#047857',
        },
        amber:   { 400:'#fbbf24', 500:'#f59e0b' },
        slate:   {
          50:  '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
          950: '#020617',
        },
      },
      animation: {
        'fade-in':      'fadeIn 0.4s ease-out both',
        'fade-in-up':   'fadeInUp 0.5s ease-out both',
        'fade-in-down': 'fadeInDown 0.4s ease-out both',
        'slide-in-left':'slideInLeft 0.4s ease-out both',
        'scale-in':     'scaleIn 0.3s ease-out both',
        'shimmer':      'shimmer 1.8s ease-in-out infinite',
        'pulse-glow':   'pulse-glow 3s ease-in-out infinite',
      },
      transitionTimingFunction: {
        'spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    }
  },
  plugins: []
}
