import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        ink: {
          950: '#080810',
          900: '#0f0f1a',
          850: '#161625',
          800: '#1f1f31',
        },
        neon: {
          pink: '#e1306c',
          orange: '#f77737',
          violet: '#833ab4',
        },
      },
      boxShadow: {
        glow: '0 0 0 3px rgba(225, 48, 108, 0.18)',
        card: '0 18px 40px rgba(8, 8, 16, 0.45)',
      },
      backgroundImage: {
        'ig-gradient': 'linear-gradient(135deg, #f77737 0%, #e1306c 42%, #833ab4 100%)',
        'page-mist': 'radial-gradient(circle at 30% -10%, rgba(225, 48, 108, 0.20), transparent 45%), radial-gradient(circle at 85% 0%, rgba(131, 58, 180, 0.18), transparent 45%), linear-gradient(180deg, #080810 0%, #0b0b15 100%)',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulsebar: {
          '0%, 100%': { transform: 'scaleX(0.98)', opacity: '0.92' },
          '50%': { transform: 'scaleX(1)', opacity: '1' },
        },
      },
      animation: {
        rise: 'rise 260ms ease-out',
        pulsebar: 'pulsebar 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
