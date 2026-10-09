import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'

// Círculo de perfil (mockup Figma, "topbar" de "2 · Listado de trámites") con
// menú desplegable para cerrar sesión.
export default function UserMenu() {
  const { usuario, cerrarSesion } = useAuth()
  const [abierto, setAbierto] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!abierto) return
    function alHacerClicFuera(e) {
      if (ref.current && !ref.current.contains(e.target)) setAbierto(false)
    }
    document.addEventListener('mousedown', alHacerClicFuera)
    return () => document.removeEventListener('mousedown', alHacerClicFuera)
  }, [abierto])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        aria-label="Menú de usuario"
        className="bg-line hover:bg-line-strong transition-colors size-[34px] rounded-full shrink-0"
        title={usuario?.nombre}
      />
      {abierto && (
        <div className="absolute right-0 top-[calc(100%+8px)] bg-surface border border-line rounded-[10px] shadow-lg w-56 py-2 z-10">
          <div className="px-4 py-2 border-b border-line">
            <p className="text-sm font-medium text-ink-primary truncate">{usuario?.nombre}</p>
            <p className="text-xs text-ink-muted truncate">{usuario?.rol_nombre}</p>
          </div>
          <button
            type="button"
            onClick={cerrarSesion}
            className="w-full text-left text-sm font-medium text-ink-primary hover:bg-canvas px-4 py-2.5 transition-colors"
          >
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  )
}
