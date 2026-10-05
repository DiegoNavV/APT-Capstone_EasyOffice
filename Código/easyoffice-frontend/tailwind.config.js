/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Tokens tal como quedaron en el mockup de Figma (página "Mockup
        // Cliente", pantalla "1 · Login"). Son provisionales igual que en el
        // mockup -> falta reemplazarlos cuando Easy Office confirme su
        // paleta de marca real para el panel interno.
        brand: {
          primary: "#0ead84",
          dark: "#0c9573"
        },
        ink: {
          primary: "#1a2b42",
          secondary: "#5b6b7f",
          muted: "#8a97a6",
          link: "#1d6fb8"
        },
        surface: "#ffffff",
        canvas: "#f4f6f8",
        line: "#dde3e9"
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
}
