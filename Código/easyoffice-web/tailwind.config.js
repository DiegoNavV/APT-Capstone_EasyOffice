/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#22B14C",   // verde corporativo Easy Office (tomado de captura real)
          dark: "#178A3A",
          light: "#E8F9EE"
        },
        accent: "#22B14C",
        ink: "#111111"
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
}
