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
      },
      keyframes: {
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-20px) translateX(-50%)' },
          '100%': { opacity: '1', transform: 'translateY(0) translateX(-50%)' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(-4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        slideDown: 'slideDown 0.3s ease-out forwards',
        fadeIn: 'fadeIn 0.2s ease-out forwards',
      },
    }
  },
  plugins: [],
};
