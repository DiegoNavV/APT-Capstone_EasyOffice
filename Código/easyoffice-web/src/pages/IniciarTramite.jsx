import { useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'

// Servicios disponibles en el MVP (caso A: 100% automatizado, sin revisión humana).
// TODO: reemplazar por un fetch a GET /api/servicios cuando el backend esté listo.
const SERVICIOS_MVP = [
  { id: 1, nombre: 'Contrato de servicio' },
  { id: 2, nombre: 'Autorización de domicilio tributario' }
]

const PASOS = ['Selecciona el trámite', 'Completa tus datos', 'Confirma y genera']

export default function IniciarTramite() {
  const [paso, setPaso] = useState(0)
  const [servicioId, setServicioId] = useState('')
  const [datosCliente, setDatosCliente] = useState({ nombre: '', rut: '', email: '', telefono: '' })
  const [codigoGenerado, setCodigoGenerado] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)

  const avanzar = () => setPaso((p) => Math.min(p + 1, PASOS.length - 1))
  const retroceder = () => setPaso((p) => Math.max(p - 1, 0))

  async function generarDocumento() {
    setEnviando(true)
    setError(null)
    try {
      // TODO: reemplazar por POST /api/tramites cuando el backend esté listo.
      // El backend debe: crear el trámite, generar codigo_seguimiento único,
      // generar el documento con la plantilla del servicio y devolverlo firmado.
      await new Promise((resolve) => setTimeout(resolve, 1200))
      const codigoSimulado = Math.random().toString(36).slice(2, 10).toUpperCase()
      setCodigoGenerado(codigoSimulado)
      avanzar()
    } catch (err) {
      setError('No pudimos generar tu documento. Intenta nuevamente en unos minutos.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      <main className="flex-1 py-12">
        <div className="max-w-2xl mx-auto px-4 sm:px-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 text-center">
            Iniciar trámite
          </h1>
          <p className="mt-2 text-gray-600 text-center">
            Sin necesidad de registrarte. Al finalizar recibirás un código de seguimiento.
          </p>

          {/* Indicador de pasos */}
          <div className="mt-8 flex items-center justify-center gap-2">
            {PASOS.map((label, i) => (
              <div key={label} className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                    ${i <= paso ? 'bg-primary text-white' : 'bg-gray-200 text-gray-500'}`}
                >
                  {i + 1}
                </div>
                {i < PASOS.length - 1 && <div className="w-8 h-px bg-gray-300" />}
              </div>
            ))}
          </div>

          <div className="mt-8 bg-white rounded-xl border border-gray-200 p-6 sm:p-8">
            {paso === 0 && (
              <div>
                <h2 className="font-semibold text-gray-900 mb-4">{PASOS[0]}</h2>
                <div className="space-y-3">
                  {SERVICIOS_MVP.map((servicio) => (
                    <label
                      key={servicio.id}
                      className={`flex items-center gap-3 border rounded-lg px-4 py-3 cursor-pointer transition-colors
                        ${servicioId === servicio.id ? 'border-primary bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`}
                    >
                      <input
                        type="radio"
                        name="servicio"
                        value={servicio.id}
                        checked={servicioId === servicio.id}
                        onChange={() => setServicioId(servicio.id)}
                        className="accent-primary"
                      />
                      <span className="text-sm font-medium text-gray-800">{servicio.nombre}</span>
                    </label>
                  ))}
                </div>
                <button
                  type="button"
                  disabled={!servicioId}
                  onClick={avanzar}
                  className="mt-6 w-full bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
                >
                  Continuar
                </button>
              </div>
            )}

            {paso === 1 && (
              <div>
                <h2 className="font-semibold text-gray-900 mb-4">{PASOS[1]}</h2>
                <div className="grid gap-4">
                  <Campo
                    label="Nombre completo"
                    value={datosCliente.nombre}
                    onChange={(v) => setDatosCliente((d) => ({ ...d, nombre: v }))}
                  />
                  <Campo
                    label="RUT"
                    value={datosCliente.rut}
                    onChange={(v) => setDatosCliente((d) => ({ ...d, rut: v }))}
                  />
                  <Campo
                    label="Correo electrónico"
                    type="email"
                    value={datosCliente.email}
                    onChange={(v) => setDatosCliente((d) => ({ ...d, email: v }))}
                  />
                  <Campo
                    label="Teléfono"
                    value={datosCliente.telefono}
                    onChange={(v) => setDatosCliente((d) => ({ ...d, telefono: v }))}
                  />
                </div>
                <div className="mt-6 flex gap-3">
                  <button
                    type="button"
                    onClick={retroceder}
                    className="flex-1 border border-gray-300 text-gray-700 font-semibold py-3 rounded-lg hover:bg-gray-50"
                  >
                    Atrás
                  </button>
                  <button
                    type="button"
                    disabled={!datosCliente.nombre || !datosCliente.rut}
                    onClick={avanzar}
                    className="flex-1 bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
                  >
                    Continuar
                  </button>
                </div>
              </div>
            )}

            {paso === 2 && !codigoGenerado && (
              <div>
                <h2 className="font-semibold text-gray-900 mb-4">{PASOS[2]}</h2>
                <p className="text-sm text-gray-600 mb-4">
                  Importante: para continuar, tu pago (100% del valor del trámite) debe estar
                  confirmado con Easy Office. Si ya realizaste el pago manual, presiona
                  "Generar documento con firma".
                </p>
                {error && <p className="text-sm text-red-600 mb-4">{error}</p>}
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={retroceder}
                    className="flex-1 border border-gray-300 text-gray-700 font-semibold py-3 rounded-lg hover:bg-gray-50"
                  >
                    Atrás
                  </button>
                  <button
                    type="button"
                    disabled={enviando}
                    onClick={generarDocumento}
                    className="flex-1 bg-accent hover:bg-amber-500 disabled:opacity-60 text-white font-semibold py-3 rounded-lg transition-colors"
                  >
                    {enviando ? 'Generando...' : 'Generar documento con firma'}
                  </button>
                </div>
              </div>
            )}

            {codigoGenerado && (
              <div className="text-center">
                <p className="text-sm text-gray-600">Tu trámite fue generado correctamente.</p>
                <p className="mt-4 text-xs uppercase tracking-wide text-gray-500">
                  Tu código de seguimiento
                </p>
                <p className="mt-1 text-3xl font-extrabold text-primary tracking-widest">
                  {codigoGenerado}
                </p>
                <p className="mt-4 text-sm text-gray-600">
                  Guarda este código: lo necesitarás para consultar el estado de tu trámite y
                  descargar tu documento firmado.
                </p>
                <Link
                  to="/seguimiento"
                  className="mt-6 inline-block bg-primary hover:bg-primary-dark text-white font-semibold px-6 py-3 rounded-lg transition-colors"
                >
                  Ir a consultar mi trámite
                </Link>
              </div>
            )}
          </div>
        </div>
      </main>

      <Footer />
    </div>
  )
}

function Campo({ label, value, onChange, type = 'text' }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
    </label>
  )
}
