import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'

// Colores del avatar. Cada agente tiene siempre el mismo, según su nombre.
const COLORES = ['bg-emerald-600', 'bg-sky-600', 'bg-violet-600', 'bg-amber-600', 'bg-rose-600', 'bg-teal-600']

// "Diego Admin" -> "DA". Con una sola palabra, sus dos primeras letras.
function iniciales(nombre) {
  const palabras = (nombre || '').trim().split(/\s+/).filter(Boolean)
  if (palabras.length === 0) return '?'
  if (palabras.length === 1) return palabras[0].slice(0, 2).toUpperCase()
  return (palabras[0][0] + palabras[1][0]).toUpperCase()
}

function colorPara(nombre) {
  let suma = 0
  for (const letra of nombre || '') suma += letra.charCodeAt(0)
  return COLORES[suma % COLORES.length]
}

// Avatar con las iniciales del agente (mockup Figma, "topbar" de "2 · Listado de trámites") y menú desplegable para
// cerrar sesión.
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

  const color = usuario?.nombre ? colorPara(usuario.nombre) : 'bg-line-strong'

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        aria-label="Menú de usuario"
        className={`${color} hover:opacity-90 transition-opacity size-[34px] rounded-full shrink-0 flex items-center justify-center text-[13px] font-semibold text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/50`}
        title={usuario?.nombre}
      >
        {iniciales(usuario?.nombre)}
      </button>
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