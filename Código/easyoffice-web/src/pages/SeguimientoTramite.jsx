import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import { validarCodigoSeguimiento } from '../utils/validaciones.js'

// Estados posibles definidos en historial_estado: generado, procesando_firma, en_revision (solo caso B), firmado, entregado.
const ESTADOS_LABEL = {
  generado: 'Generado',
  procesando_firma: 'Procesando firma',
  en_revision: 'En revisión',
  firmado: 'Firmado',
  entregado: 'Entregado'
}

export default function SeguimientoTramite() {
  const [searchParams] = useSearchParams()
  const [codigo, setCodigo] = useState(searchParams.get('codigo') ?? '')
  const [buscando, setBuscando] = useState(false)
  const [tramite, setTramite] = useState(null)
  const [error, setError] = useState(null)

  const codigoValido = validarCodigoSeguimiento(codigo)

  function onCambiarCodigo(valor) {
    const limpio = valor.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8)
    setCodigo(limpio)
  }

  async function consultar(e) {
    e.preventDefault()
    if (!codigoValido) {
      setError('El código debe tener 8 caracteres (letras y números).')
      return
    }
    setBuscando(true)
    setError(null)
    setTramite(null)
    try {
      const respuesta = await fetch(`${import.meta.env.VITE_API_URL}/api/tramites/codigo/${codigo}`)

      if (!respuesta.ok) {
        throw new Error('No encontrado')
      }

      const datos = await respuesta.json()
      setTramite({
        codigo_seguimiento: datos.codigo_seguimiento,
        servicio: datos.nombre_servicio,
        estado_actual: datos.estado_actual,
        documento_disponible: datos.documento_disponible
      })
    } catch {
      setError('No encontramos un trámite con ese código. Verifica e intenta nuevamente.')
    } finally {
      setBuscando(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      <main className="flex-1 py-12">
        <div className="max-w-xl mx-auto px-4 sm:px-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 text-center">
            Consultar mi trámite
          </h1>
          <p className="mt-2 text-gray-600 text-center">
            Ingresa el código de 8 caracteres que recibiste al iniciar tu trámite.
          </p>

          <form onSubmit={consultar} className="mt-8 bg-white rounded-xl border border-gray-200 p-6 sm:p-8">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Código de seguimiento</span>
              <input
                type="text"
                maxLength={8}
                value={codigo}
                onChange={(e) => onCambiarCodigo(e.target.value)}
                placeholder="Ej: A1B2C3D4"
                className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm tracking-widest text-center font-semibold focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
              />
            </label>
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            <button
              type="submit"
              disabled={buscando || !codigoValido}
              className="mt-4 w-full bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
            >
              {buscando ? 'Consultando...' : 'Consultar estado'}
            </button>
          </form>

          {tramite && (
            <div className="mt-6 bg-white rounded-xl border border-gray-200 p-6 sm:p-8">
              <p className="text-sm text-gray-500">Trámite</p>
              <p className="font-semibold text-gray-900">{tramite.servicio}</p>

              <p className="mt-4 text-sm text-gray-500">Estado actual</p>
              <span className="inline-block mt-1 px-3 py-1 rounded-full text-sm font-semibold bg-green-100 text-green-700">
                {ESTADOS_LABEL[tramite.estado_actual] ?? tramite.estado_actual}
              </span>

              {tramite.documento_disponible ? (
                <button
                  type="button"
                  className="mt-6 w-full bg-accent hover:bg-amber-500 text-white font-semibold py-3 rounded-lg transition-colors"
                >
                  Descargar documento firmado
                </button>
              ) : (
                <p className="mt-6 text-sm text-gray-600">
                  Tu documento aún se está procesando. Vuelve a consultar más tarde con el mismo código.
                </p>
              )}
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}