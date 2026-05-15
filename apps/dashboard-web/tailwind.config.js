/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        grid: {
          bg: '#0a0e1a',
          panel: '#111827',
          border: '#1f2937',
          accent: '#fbbf24',
          ok: '#10b981',
          warn: '#f59e0b',
          crit: '#ef4444',
          info: '#38bdf8',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      }
    }
  },
  plugins: [],
};
