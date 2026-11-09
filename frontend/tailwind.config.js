/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        juli: {
          bg: 'rgba(var(--color-juli-bg-rgb), <alpha-value>)',
          panel: 'rgba(var(--color-juli-panel-rgb), <alpha-value>)',
          card: '#0f172a',
          surface: '#131c31',
          border: 'rgba(var(--color-juli-border-rgb), <alpha-value>)',
          accent: 'rgba(var(--color-juli-accent-rgb), <alpha-value>)',
          glow: '#22d3ee',
          success: '#10b981',
          warning: '#f59e0b',
          error: '#ef4444',
          muted: 'rgba(var(--color-juli-muted-rgb), <alpha-value>)',
          text: '#94a3b8',
        },
        agent: {
          planner: '#6366f1',
          coder: '#06b6d4',
          reviewer: '#ef4444',
          devops: '#10b981',
          test: '#f59e0b',
          docs: '#8b5cf6',
          user: '#6b7280',
          system: '#374151',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'float': 'float 6s ease-in-out infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(6, 182, 212, 0.2)' },
          '100%': { boxShadow: '0 0 20px rgba(6, 182, 212, 0.4)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      boxShadow: {
        'glass': '0 4px 30px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03)',
        'glass-lg': '0 8px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
        'glow-sm': '0 0 10px rgba(6, 182, 212, 0.15)',
        'glow-md': '0 0 20px rgba(6, 182, 212, 0.2)',
        'glow-lg': '0 0 40px rgba(6, 182, 212, 0.25)',
      },
    },
  },
  plugins: [],
}
