/** @type {import('tailwindcss').Config} */
// Light-mode redesign — clean white cards on blue-grey canvas.
// Accent colors darkened to meet contrast on white backgrounds.

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:  '#EEF1F8',   // page canvas — light blue-grey
        bg2: '#FFFFFF',   // card surface
        t0:  '#0F172A',   // primary text — dark navy
        t1:  '#1E293B',   // secondary text
        t2:  '#475569',   // tertiary text
        t3:  '#64748B',   // muted / label text — min 4.6:1 on white
        lime:   '#16A34A', // 9-10/10 verified — green on white
        cyan:   '#2563EB', // 7-8/10 strong — blue on white
        violet: '#7C3AED',
        amber:  '#D97706', // ≤6/10 signal — amber on white
        rose:   '#E11D48',
        teal:   '#0D9488',
        z0: '#16A34A',
        z1: '#0D9488',
        z2: '#D97706',
        z3: '#EA580C',
        z4: '#991B1B',
      },
      fontFamily: {
        display: ['Outfit', 'system-ui', 'sans-serif'],
        sans:    ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono:    ['"Fira Code"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        base: '12px',
      },
      borderRadius: {
        r:     '16px',
        'r-sm': '10px',
        'r-xs': '6px',
      },
      boxShadow: {
        card:  '0 1px 3px rgba(15,23,42,0.08), 0 4px 16px rgba(15,23,42,0.06)',
        'card-md': '0 2px 8px rgba(15,23,42,0.10), 0 8px 24px rgba(15,23,42,0.06)',
        // keep glow shadows for map markers
        'glow-lime':   '0 0 24px rgba(22,163,74,.20)',
        'glow-cyan':   '0 0 24px rgba(37,99,235,.20)',
        'glow-violet': '0 0 24px rgba(124,58,237,.16)',
      },
    },
  },
  plugins: [],
};
