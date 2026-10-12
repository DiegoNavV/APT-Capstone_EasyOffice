import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext.jsx'
import Sidebar from '../components/Sidebar.jsx'

// Estructura común del panel interno (rutas /panel/*): valida la sesión una sola vez, dibuja la barra lateral y deja el espacio de la derecha
// para la vista que corresponda a la ruta (<Outlet />). Cada vista usa PaginaPanel para su encabezado y su área de contenido.
export default function Panel() {
  const { usuario, verificando } = useAuth()

  // Esperar a que termine de recuperarse la sesión (ver AuthContext.jsx)
  // antes de decidir si hay que mandar al login.
  if (verificando) return null
  if (!usuario) return <Navigate to="/" replace />

  return (
    <div className="bg-canvas flex h-screen items-start">
      <Sidebar />

      <div className="flex flex-1 flex-col h-full min-w-0">
        <Outlet />
      </div>
    </div>
  )
}