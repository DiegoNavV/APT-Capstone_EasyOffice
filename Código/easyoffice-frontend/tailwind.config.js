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
          dark: "#0c9573",
          tint: "#e6f7f1"
        },
        ink: {
          primary: "#1a2b42",
          secondary: "#5b6b7f",
          muted: "#8a97a6",
          link: "#1d6fb8"
        },
        surface: "#ffffff",
        canvas: "#f4f6f8",
        subtle: "#eef1f4",
        line: "#dde3e9",
        "line-strong": "#c4cdd6",
        // Panel interno (sidebar oscuro), pantalla "2 · Listado de trámites" del mockup.
        sidebar: {
          bg: "#14243b",
          "active-bg": "#1e3350",
          fg: "#9fb1c7"
        },
        // Pares bg/fg de StatusChip (pantalla "2 · Listado de trámites" del mockup).
        status: {
          "draft-bg": "#eef1f4",
          "draft-fg": "#5b6b7f",
          "sent-bg": "#fff3e0",
          "sent-fg": "#b7791f",
          "signed-bg": "#e4f1fd",
          "signed-fg": "#1d6fb8",
          "delivered-bg": "#e6f7f1",
          "delivered-fg": "#0a7d60",
          "rejected-bg": "#fdecec",
          "rejected-fg": "#c0392b"
        }
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
}
