import { useState } from 'react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'

// Servicios priorizados del MVP. El código de seguimiento NO se genera aquí:
// este formulario solo deja la solicitud registrada para que Easy Office
// contacte al cliente, coordine la gestión y el pago manual. El código lo
// genera después un administrador/agente desde el panel interno, una vez
// confirmado el pago, y se lo entrega al cliente por fuera del sitio.
const SERVICIOS = [
  { id: 1, nombre: 'Contrato de servicio' },
  { id: 2, nombre: 'Autorización de domicilio tributario' },
  { id: 0, nombre: 'Otro / no estoy seguro' }
]

export default function IniciarTramite() {
  const [form, setForm] = useState({
    nombre: '',
    rut: '',
    email: '',
    telefono: '',
    servicioId: '',
    mensaje: ''
  })
  const [enviando, setEnviando] = useState(false)
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState(null)

  function setCampo(campo, valor) {
    setForm((f) => ({ ...f, [campo]: valor }))
  }

  async function enviarSolicitud(e) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    try {
      // TODO: reemplazar por POST /api/solicitudes-contacto cuando el backend
      // esté listo. El backend debe registrar la solicitud (sin generar
      // codigo_seguimiento todavía) para que aparezca en el panel de
      // administradores/agentes y ellos la gestionen manualmente.
      await new Promise((resolve) => setTimeout(resolve, 900))
      setEnviado(true)
    } catch {
      setError('No pudimos enviar tu solicitud. Intenta nuevamente en unos minutos.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      <main className="flex-1 py-12">
        <div className="max-w-xl mx-auto px-4 sm:px-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-ink text-center">
            Contrata tu trámite
          </h1>
          <p className="mt-2 text-gray-600 text-center">
            Déjanos tus datos y un ejecutivo de Easy Office se contactará contigo para coordinar
            la gestión y el pago. Una vez confirmado el pago, te enviaremos tu código de
            seguimiento para completar el trámite online.
          </p>

          {!enviado ? (
            <form
              onSubmit={enviarSolicitud}
              className="mt-8 bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-4"
            >
              <Campo
                label="Servicio de interés"
                tipo="select"
                value={form.servicioId}
                onChange={(v) => setCampo('servicioId', v)}
              >
                <option value="" disabled>Selecciona un servicio</option>
                {SERVICIOS.map((s) => (
                  <option key={s.id} value={s.id}>{s.nombre}</option>
                ))}
              </Campo>

              <Campo
                label="Nombre completo"
                value={form.nombre}
                onChange={(v) => setCampo('nombre', v)}
              />
              <Campo
                label="RUT"
                value={form.rut}
                onChange={(v) => setCampo('rut', v)}
              />
              <Campo
                label="Correo electrónico"
                type="email"
                value={form.email}
                onChange={(v) => setCampo('email', v)}
              />
              <Campo
                label="Teléfono"
                value={form.telefono}
                onChange={(v) => setCampo('telefono', v)}
              />
              <Campo
                label="Mensaje (opcional)"
                tipo="textarea"
                value={form.mensaje}
                onChange={(v) => setCampo('mensaje', v)}
              />

              {error && <p className="text-sm text-red-600">{error}</p>}

              <button
                type="submit"
                disabled={enviando || !form.nombre || !form.rut || !form.servicioId}
                className="w-full bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-md transition-colors"
              >
                {enviando ? 'Enviando...' : 'Enviar solicitud'}
              </button>
            </form>
          ) : (
            <div className="mt-8 bg-white rounded-xl border border-gray-200 p-6 sm:p-8 text-center">
              <p className="text-lg font-semibold text-ink">¡Solicitud enviada!</p>
              <p className="mt-2 text-sm text-gray-600">
                Un ejecutivo de Easy Office se comunicará contigo a la brevedad para coordinar la
                gestión y el pago. Cuando el pago esté confirmado, recibirás tu código de
                seguimiento para completar el trámite desde la web.
              </p>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}

function Campo({ label, value, onChange, type = 'text', tipo = 'input', children }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      {tipo === 'select' && (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
        >
          {children}
        </select>
      )}
      {tipo === 'textarea' && (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
        />
      )}
      {tipo === 'input' && (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
        />
      )}
    </label>
  )
}