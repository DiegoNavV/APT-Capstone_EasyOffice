import { Link, useLocation, useNavigate } from 'react-router-dom'

const NAV_LINKS = [
  { label: 'Inicio', id: 'inicio' },
  { label: 'Domicilio tributario', id: 'domicilio-tributario' },
  { label: 'Contabilidad', id: 'contabilidad' },
  { label: 'Firmas Electrónicas', id: 'firmas-electronicas' },
  { label: 'Asesoría Empresas', id: 'empresa-en-1-dia' },
  { label: 'Rebaja Tributaria', id: 'rebaja-tributaria' }
]

export default function Header({ onIniciarTramite }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const enHome = pathname === '/'

  // En el home abre la ventana emergente; en las demás páginas lleva al formulario.
  function iniciarTramite() {
    if (onIniciarTramite) onIniciarTramite()
    else navigate('/iniciar-tramite')
  }

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
      <header className="w-full bg-white border-b border-gray-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-24">
          <button
            type="button"
            onClick={iniciarTramite}
            className="..." // deja las mismas clases que ya tenía el botón verde
          >
            Inicia tu trámite
          </button>

          <nav className="hidden lg:flex items-center gap-6">
            {NAV_LINKS.map((link) => {
              const activo = enHome && link.id === 'inicio'
              const clases = `text-sm font-medium pb-1 border-b-2 transition-colors
                  ${activo
                    ? 'text-primary border-primary'
                    : 'text-gray-700 border-transparent hover:text-primary hover:border-primary'}`

              // Dentro del home se salta a la sección; desde otra página se vuelve al home y se baja a ella.
              return enHome ? (
                <a key={link.id} href={`#${link.id}`} className={clases}>
                  {link.label}
                </a>
              ) : (
                <Link key={link.id} to={{ pathname: '/', hash: `#${link.id}` }} className={clases}>
                  {link.label}
                </Link>
              )
            })}
          </nav>

          <button
            type="button"
            onClick={iniciarTramite}
            className="bg-primary hover:bg-primary-dark text-white text-sm font-bold text-center leading-tight px-4 py-3 rounded-md shadow-sm transition-colors"
          >
            Inicia tu<br />trámite
          </button>
        </div>
      </header>
    </>
  )
}