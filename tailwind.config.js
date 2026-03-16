/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./raceanalyzer/templates/**/*.html"],
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        'ra-bg': '#f0edea',
        'ra-surface': '#ffffff',
        'ra-sidebar': '#e2ddd8',
        'ra-accent': '#ff6b35',
        'ra-text': '#333333',
        'ra-text-muted': '#666666',
      },
    },
  },
  plugins: [],
}
