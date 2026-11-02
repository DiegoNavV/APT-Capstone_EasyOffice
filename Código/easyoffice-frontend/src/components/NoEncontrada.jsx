import { Link, useLocation } from 'react-router-dom'
import PaginaPanel from './PaginaPanel.jsx'

// Pantalla para cualquier ruta del panel que no existe (ver App.jsx). Se dibuja dentro del layout de Panel.jsx, así el agente
// conserva la barra lateral y su menú, y puede seguir desde ahí.
export default function NoEncontrada() {
  const { pathname } = useLocation()

  return (
    <PaginaPanel titulo="Página no encontrada">
      <div className="h-full flex flex-col items-center justify-center text-center">
        <p className="text-6xl font-bold text-brand-primary">404</p>
        <p className="mt-3 text-2xl font-semibold text-ink-primary">Esta página no existe</p>
        <p className="mt-2 max-w-md text-sm text-ink-muted">
          No hay nada en <span className="font-mono text-ink-primary break-all">{pathname}</span>. Revisa la dirección o
          elige una sección en el menú de la izquierda.
        </p>
        <Link
          to="/panel/solicitudes"
          className="mt-6 bg-brand-primary hover:bg-brand-dark text-white text-sm font-semibold px-6 py-3 rounded-[10px] transition-colors"
        >
          Ir a Solicitudes
        </Link>
      </div>
    </PaginaPanel>
  )
}
