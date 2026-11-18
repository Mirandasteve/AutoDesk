/**
 * Design tokens for the whole product.
 *
 * Everything visual is derived from this file plus the component layer in
 * `src/index.css`, so re-skinning the portal means editing these two files
 * rather than nineteen pages.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        // Primary action colour. Used by buttons, focus rings, active nav and
        // the classifier confidence meter so "brand" always means one thing.
        brand: {
          50: '#eef3ff',
          100: '#dfe8ff',
          200: '#c5d3ff',
          300: '#9bb3fd',
          400: '#6d8bfa',
          500: '#4a68f5',
          600: '#2f4ae8',
          700: '#2838cf',
          800: '#2831a8',
          900: '#252e85',
          950: '#161b48',
        },
        // Secondary hue, used only for gradients and decorative highlights so
        // it never competes with brand for meaning.
        accent: {
          50: '#f5f2ff',
          100: '#ece5ff',
          200: '#dbcdff',
          300: '#c1a6ff',
          400: '#a274fb',
          500: '#8a4cf3',
          600: '#7c2ce0',
          700: '#6c1ec0',
          800: '#591a9a',
          900: '#4a1a7c',
        },
        // Neutral canvas tokens, so `bg-canvas` never has to be re-guessed.
        canvas: '#f5f7fc',
        surface: '#ffffff',
        hairline: '#e6eaf2',
        ink: {
          DEFAULT: '#101828',
          soft: '#475467',
          muted: '#667085',
          faint: '#98a2b3',
        },
      },
      boxShadow: {
        // Layered so cards read as raised paper rather than outlined boxes.
        xs: '0 1px 2px 0 rgb(16 24 40 / 0.05)',
        card: '0 1px 2px 0 rgb(16 24 40 / 0.04), 0 1px 3px 0 rgb(16 24 40 / 0.06)',
        'card-md': '0 4px 8px -2px rgb(16 24 40 / 0.06), 0 2px 4px -2px rgb(16 24 40 / 0.04)',
        'card-lg': '0 12px 20px -8px rgb(16 24 40 / 0.10), 0 4px 8px -4px rgb(16 24 40 / 0.06)',
        'card-xl': '0 20px 32px -12px rgb(16 24 40 / 0.16), 0 8px 12px -8px rgb(16 24 40 / 0.08)',
        pop: '0 24px 48px -12px rgb(16 24 40 / 0.25)',
        nav: '2px 0 12px -2px rgb(16 24 40 / 0.08)',
        glow: '0 0 0 1px rgb(47 74 232 / 0.10), 0 10px 28px -10px rgb(47 74 232 / 0.32)',
        inset: 'inset 0 1px 0 0 rgb(255 255 255 / 0.6)',
      },
      borderRadius: {
        '2.5xl': '1.25rem',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #4a68f5 0%, #7c2ce0 100%)',
        'brand-gradient-soft': 'linear-gradient(135deg, #dfe8ff 0%, #ece5ff 100%)',
        'canvas-mesh':
          'radial-gradient(60rem 40rem at 12% -10%, #e5edff 0%, transparent 55%), radial-gradient(48rem 32rem at 100% 0%, #f0e9ff 0%, transparent 50%)',
        'hero-mesh':
          'radial-gradient(46rem 34rem at 8% 4%, rgba(122,140,255,0.55) 0%, transparent 60%), radial-gradient(38rem 30rem at 92% 12%, rgba(168,116,251,0.45) 0%, transparent 55%), radial-gradient(40rem 30rem at 50% 110%, rgba(47,74,232,0.35) 0%, transparent 60%)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'translateY(8px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'slide-in-left': {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgb(47 74 232 / 0.35)' },
          '70%': { boxShadow: '0 0 0 8px rgb(47 74 232 / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(47 74 232 / 0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 160ms ease-out',
        'fade-up': 'fade-up 220ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'scale-in': 'scale-in 200ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'slide-in-left': 'slide-in-left 240ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'pulse-ring': 'pulse-ring 2s ease-out infinite',
      },
      transitionTimingFunction: {
        smooth: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
