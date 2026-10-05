import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 ya lo usa easyoffice-web (sitio público). Son dos apps de
    // frontend separadas (ver Definiciones_Desarrollo_CRM_EasyOffice.docx,
    // sección 6), así que corren en puertos distintos para poder levantar
    // ambas a la vez en desarrollo.
    port: 5174,
    // Hosts externos desde los que se permite abrir el servidor de desarrollo
    // (Vite bloquea por defecto cualquier host que no sea localhost).
    // Va solo el dominio: sin "https://" ni "/" final.
    allowedHosts: ['humiliate-unlimited-greasily.ngrok-free.dev']
  }
})
