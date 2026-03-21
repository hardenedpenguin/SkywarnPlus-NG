/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/skywarnplus_ng/web/templates/**/*.html"],
  // Match dashboard theme toggle (see base.html data-theme on <html>)
  darkMode: ["selector", '[data-theme="dark"] &'],
  theme: {
    extend: {},
  },
  plugins: [],
};
