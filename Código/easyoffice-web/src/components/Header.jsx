import { Link } from 'react-router-dom'

const NAV_LINKS = [
  { label: 'Inicio', href: '#inicio', active: true },
  { label: 'Domicilio tributario', href: '#domicilio-tributario' },
  { label: 'Contabilidad', href: '#contabilidad' },
  { label: 'Firmas Electrónicas', href: '#firmas-electronicas' },
  { label: 'Asesoría Empresas', href: '#asesoria-empresas' },
  { label: 'Rebaja Tributaria', href: '#rebaja-tributaria' }
]

export default function Header({ onIniciarTramite }) {
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
          <Link to="/" className="flex items-center gap-2">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="14" cy="20" r="9" stroke="#22B14C" strokeWidth="4" />
              <circle cx="26" cy="20" r="9" stroke="#22B14C" strokeWidth="4" />
            </svg>
            <span className="text-lg font-bold text-ink leading-tight">
              easy<br />office
            </span>
          </Link>

          <nav className="hidden lg:flex items-center gap-6">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className={`text-sm font-medium pb-1 border-b-2 transition-colors
                  ${link.active
                    ? 'text-primary border-primary'
                    : 'text-gray-700 border-transparent hover:text-primary hover:border-primary'}`}
              >
                {link.label}
              </a>
            ))}
          </nav>

          <button
            type="button"
            onClick={onIniciarTramite}
            className="bg-primary hover:bg-primary-dark text-white text-sm font-bold text-center leading-tight px-4 py-3 rounded-md shadow-sm transition-colors"
          >
            Inicia tu<br />trámite
          </button>
        </div>
      </header>
    </>
  )
}
