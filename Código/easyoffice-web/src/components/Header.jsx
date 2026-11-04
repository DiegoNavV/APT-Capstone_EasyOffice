import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import IniciarTramiteModal from './IniciarTramiteModal.jsx'
import { EnlaceSeccion, NAV_LINKS } from './enlaces.jsx'

export default function Header({ onIniciarTramite }) {
  const { pathname } = useLocation()
  const enHome = pathname === '/'
  const [modalAbierto, setModalAbierto] = useState(false)
  // Menú de celular y tablet (debajo de lg). En escritorio se usa el <nav> de siempre.
  const [menuAbierto, setMenuAbierto] = useState(false)
  const menuRef = useRef(null)

  // Si la página entrega su propia función (el inicio), se usa esa. En todas las demás páginas el header abre su
  // propia ventana emergente para ingresar el código, así el botón funciona igual en todo el sitio.
  function iniciarTramite() {
    setMenuAbierto(false)
    if (onIniciarTramite) onIniciarTramite()
    else setModalAbierto(true)
  }

  // El menú se cierra con Escape o al tocar fuera de él (o de su botón).
  useEffect(() => {
    if (!menuAbierto) return undefined
    function alPresionarTecla(e) {
      if (e.key === 'Escape') setMenuAbierto(false)
    }
    function alTocarFuera(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuAbierto(false)
    }
    document.addEventListener('keydown', alPresionarTecla)
    document.addEventListener('pointerdown', alTocarFuera)
    return () => {
      document.removeEventListener('keydown', alPresionarTecla)
      document.removeEventListener('pointerdown', alTocarFuera)
    }
  }, [menuAbierto])

  return (
    <>
      {/* Barra superior */}
      <div className="bg-primary-light text-ink text-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-11 flex items-center justify-between">
          <span className="font-medium">Más de 5000 emprendimientos exitosos</span>
          <a
            href="tel:+56222777781"
            className="hidden sm:flex items-center gap-2 bg-primary text-white font-semibold px-4 py-1.5 rounded-full"
          >
            +56 2 2277 7781
          </a>
        </div>
      </div>

      {/* Header principal */}
      <header ref={menuRef} className="w-full bg-white border-b border-gray-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-20 lg:h-24">
          <div className="flex items-center gap-8">
            <Link to="/" aria-label="Easy Office, ir al inicio" className="flex flex-col items-center leading-none">
              <img src="/favicon.png" alt="" width="48" height="48" className="w-12 h-12" />
              <span className="mt-0.5 text-[13px] tracking-[0.18em] text-gray-600">easy office</span>
            </Link>

            <nav className="hidden lg:flex items-center gap-6">
              {NAV_LINKS.map((link) => {
                const activo = enHome && link.id === 'inicio'
                const clases = `text-sm font-medium pb-1 border-b-2 transition-colors
                    ${activo
                      ? 'text-primary border-primary'
                      : 'text-gray-700 border-transparent hover:text-primary hover:border-primary'}`
                return <EnlaceSeccion key={link.id} enlace={link} enHome={enHome} className={clases} />
              })}
            </nav>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={iniciarTramite}
              className="bg-primary hover:bg-primary-dark text-white text-sm font-bold text-center leading-tight px-4 py-3 rounded-md shadow-sm transition-colors"
            >
              Inicia tu<br />trámite
            </button>

            <button
              type="button"
              onClick={() => setMenuAbierto((v) => !v)}
              aria-expanded={menuAbierto}
              aria-controls="menu-celular"
              aria-label={menuAbierto ? 'Cerrar menú' : 'Abrir menú'}
              className="lg:hidden size-11 flex items-center justify-center rounded-md text-gray-700 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                {menuAbierto ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
              </svg>
            </button>
          </div>
        </div>

        {/* Menú desplegable de celular y tablet: queda bajo el header y, si no cabe en el alto, hace scroll propio. */}
        {menuAbierto && (
          <nav
            id="menu-celular"
            aria-label="Secciones"
            className="lg:hidden absolute inset-x-0 top-full bg-white border-b border-gray-200 shadow-lg max-h-[calc(100dvh-5rem)] overflow-y-auto"
          >
            <ul className="max-w-7xl mx-auto px-4 sm:px-6 py-2">
              {NAV_LINKS.map((link) => {
                const activo = enHome && link.id === 'inicio'
                return (
                  <li key={link.id}>
                    <EnlaceSeccion
                      enlace={link}
                      enHome={enHome}
                      onClick={() => setMenuAbierto(false)}
                      className={`flex min-h-[44px] items-center rounded-md px-3 text-base font-medium transition-colors ${
                        activo ? 'text-primary bg-primary-light' : 'text-gray-700 hover:text-primary hover:bg-gray-50'
                      }`}
                    />
                  </li>
                )
              })}
            </ul>
          </nav>
        )}
      </header>

      {/* Solo se usa cuando la página no trae su propia ventana (todas menos el inicio). */}
      <IniciarTramiteModal open={modalAbierto} onClose={() => setModalAbierto(false)} />
    </>
  )
}
