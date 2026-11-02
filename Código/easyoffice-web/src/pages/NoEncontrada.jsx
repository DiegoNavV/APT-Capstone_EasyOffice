import { Link, useLocation } from 'react-router-dom'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'

// Se muestra para cualquier dirección que no coincide con una ruta del sitio (ver App.jsx).
export default function NoEncontrada() {
  const { pathname } = useLocation()

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      <main className="flex-1 flex items-center py-16">
        <div className="max-w-xl mx-auto px-4 sm:px-6 text-center">
          <p className="text-6xl sm:text-7xl font-bold text-primary">404</p>
          <h1 className="mt-4 text-2xl sm:text-3xl font-bold text-gray-900">
            No encontramos esta página
          </h1>
          <p className="mt-3 text-gray-600">
            La dirección <span className="font-mono text-sm break-all text-gray-800">{pathname}</span> no
            existe o fue movida. Revisa que esté bien escrita, o sigue desde alguna de estas opciones.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/"
              className="bg-primary hover:bg-primary-dark text-white font-semibold py-3 px-6 rounded-lg transition-colors"
            >
              Ir al inicio
            </Link>
            <Link
              to="/seguimiento"
              className="bg-white border border-gray-300 hover:border-primary hover:text-primary text-gray-700 font-semibold py-3 px-6 rounded-lg transition-colors"
            >
              Consultar mi trámite
            </Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  )
}
