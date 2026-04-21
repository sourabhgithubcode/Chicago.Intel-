/** @type {import('tailwindcss').Config} */
// Design tokens extracted from chicago-v4-final.html.
// Aurora/glassmorphism system with Outfit + DM Sans + Fira Code.

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#050810',
        bg2: '#08101e',
        t0: '#f5f8ff',
        t1: '#d0e0f8',
        t2: '#a8bcd8',
        t3: '#4a6080',
        lime: '#a8ff78',
        cyan: '#38bdf8',
        violet: '#c084fc',
        amber: '#fcd34d',
        rose: '#fb7185',
        teal: '#2dd4bf',
        z0: '#a8ff78',
        z1: '#6ee7b7',
        z2: '#fcd34d',
        z3: '#fb923c',
        z4: '#7c3322',
      },
      fontFamily: {
        display: ['Outfit', 'system-ui', 'sans-serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"Fira Code"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        base: '12px',
      },
      borderRadius: {
        r: '18px',
        'r-sm': '11px',
        'r-xs': '7px',
      },
      boxShadow: {
        'glow-lime': '0 0 32px rgba(168,255,120,.14)',
        'glow-cyan': '0 0 32px rgba(56,189,248,.14)',
        'glow-violet': '0 0 32px rgba(192,132,252,.12)',
        cell: '0 4px 24px rgba(0,0,0,.4), 0 1px 0 rgba(255,255,255,.05) inset',
      },
    },
  },
  plugins: [],
};
