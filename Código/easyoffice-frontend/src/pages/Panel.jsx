import { Link, Navigate } from 'react-router-dom' // NUEVO: se agregó Link
import { useAuth } from '../lib/AuthContext.jsx'

// Placeholder: el panel real (listado de trámites, clientes, etc. del
// mockup de Figma) todavía no está construido. Esta pantalla solo confirma
// que el login funcionó de punta a punta.

export default function Panel() {
  const { usuario, verificando, cerrarSesion } = useAuth()

  // Mientras se intenta recuperar la sesión con el refresh token (al cargar
  // la página, ver AuthContext.jsx) todavía no se sabe si hay sesión o no;
  // redirigir antes de tiempo mandaría a un usuario con sesión válida de
  // vuelta al login.
  if (verificando) return null
  if (!usuario) return <Navigate to="/" replace />

  return (
    <div className="bg-canvas min-h-screen flex items-center justify-center px-4">
      <div className="bg-surface border border-line rounded-2xl p-10 max-w-[440px] w-full text-center">
        <h1 className="text-xl font-semibold text-ink-primary">Bienvenido, {usuario.nombre}</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Sesión iniciada como <span className="font-medium">{usuario.rol_nombre}</span>.
        </p>
        <p className="mt-1 text-xs text-ink-muted">
          El panel real (trámites, clientes, reportes) todavía no está construido.
        </p>
        {/* NUEVO: enlace a la pantalla de solicitudes */}
        <Link
          to="/panel/solicitudes"
          className="mt-6 inline-block bg-brand-primary hover:bg-brand-dark text-white text-sm font-semibold px-6 py-3 rounded-[10px] transition-colors"
        >
          Ver solicitudes de contacto
        </Link>
        {/* NUEVO: el botón de cerrar sesión ahora va dentro de un div */}
        <div>
          <button
            type="button"
            onClick={cerrarSesion}
            className="mt-6 text-sm font-medium text-ink-link hover:underline"
          >
            Cerrar sesión
          </button>
        </div>
      </div>
    </div>
  )
}