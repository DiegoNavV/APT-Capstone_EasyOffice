import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './lib/AuthContext.jsx'

import LogIn from './pages/LogIn.jsx'
import Panel from './pages/Panel.jsx'
import Solicitudes from './pages/Solicitudes.jsx'
import Tramites from './pages/Tramites.jsx'
import Plantillas from './pages/Plantillas.jsx'
import Reportes from './pages/Reportes.jsx'
import Proximamente from './components/Proximamente.jsx'

// Todas las rutas /panel/* comparten el layout de Panel.jsx (sidebar + sesión).
// Mientras no exista un home del panel, /panel y cualquier ruta desconocida llevan a Solicitudes, que es el módulo ya construido.
// Reportes ya está conectado a GET /api/tramites/reporte; el backend decide con `puede_ver` quién la ve (hoy solo administradores).
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LogIn />} />
        <Route path="/panel" element={<Panel />}>
          <Route index element={<Navigate to="/panel/solicitudes" replace />} />
          <Route path="solicitudes" element={<Solicitudes />} />
          <Route path="tramites" element={<Tramites />} />
          <Route path="clientes" element={<Proximamente titulo="Clientes" />} />
          <Route path="plantillas" element={<Plantillas />} />
          <Route path="reportes" element={<Reportes />} />
          <Route path="configuracion" element={<Proximamente titulo="Configuración" />} />
          <Route path="*" element={<Navigate to="/panel/solicitudes" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}