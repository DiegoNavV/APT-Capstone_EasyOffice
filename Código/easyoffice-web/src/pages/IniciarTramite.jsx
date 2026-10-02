import { useState } from 'react'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import {
  formatearRut,
  validarRut,
  validarEmail,
  validarTelefono,
  validarNombre
} from '../utils/validaciones.js'

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

const MENSAJE_MAX = 500

export default function IniciarTramite() {
  const [form, setForm] = useState({
    nombre: '',
    rut: '',
    email: '',
    telefono: '',
    servicioId: '',
    mensaje: ''
  })
  const [tocado, setTocado] = useState({})
  const [enviando, setEnviando] = useState(false)
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState(null)

  function setCampo(campo, valor) {
    if (campo === 'rut') valor = formatearRut(valor)
    if (campo === 'mensaje') valor = valor.slice(0, MENSAJE_MAX)
    setForm((f) => ({ ...f, [campo]: valor }))
  }

  function marcarTocado(campo) {
    setTocado((t) => ({ ...t, [campo]: true }))
  }

  const errores = {
    servicioId: form.servicioId === '' ? 'Selecciona un servicio.' : null,
    nombre: !validarNombre(form.nombre) ? 'Ingresa tu nombre completo (solo letras, mínimo 3 caracteres).' : null,
    rut: !validarRut(form.rut) ? 'El RUT ingresado no es válido.' : null,
    email: !validarEmail(form.email) ? 'Ingresa un correo electrónico válido.' : null,
    telefono: !validarTelefono(form.telefono) ? 'Ingresa un teléfono chileno válido (ej: +56 9 1234 5678).' : null
  }
  const formValido = Object.values(errores).every((e) => !e)

  function mostrarError(campo) {
    return tocado[campo] && errores[campo] ? errores[campo] : null
  }

  async function enviarSolicitud(e) {
    e.preventDefault()
    setTocado({ servicioId: true, nombre: true, rut: true, email: true, telefono: true })
    if (!formValido) return

    setEnviando(true)
    setError(null)
    try {
      const respuesta = await fetch(`${import.meta.env.VITE_API_URL}/api/solicitudes-contacto`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nombre: form.nombre,
          rut: form.rut,
          email: form.email,
          telefono: form.telefono,
          servicio_id: form.servicioId ? Number(form.servicioId) : null,
          mensaje: form.mensaje || null
        })
      })

      if (!respuesta.ok) {
        throw new Error('Respuesta no exitosa del servidor')
      }

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
                onBlur={() => marcarTocado('servicioId')}
                error={mostrarError('servicioId')}
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
                onBlur={() => marcarTocado('nombre')}
                error={mostrarError('nombre')}
              />
              <Campo
                label="RUT"
                value={form.rut}
                onChange={(v) => setCampo('rut', v)}
                onBlur={() => marcarTocado('rut')}
                error={mostrarError('rut')}
                placeholder="12.345.678-9"
              />
              <Campo
                label="Correo electrónico"
                type="email"
                value={form.email}
                onChange={(v) => setCampo('email', v)}
                onBlur={() => marcarTocado('email')}
                error={mostrarError('email')}
              />
              <Campo
                label="Teléfono"
                value={form.telefono}
                onChange={(v) => setCampo('telefono', v)}
                onBlur={() => marcarTocado('telefono')}
                error={mostrarError('telefono')}
                placeholder="+56 9 1234 5678"
              />
              <Campo
                label={`Mensaje (opcional) — ${form.mensaje.length}/${MENSAJE_MAX}`}
                tipo="textarea"
                value={form.mensaje}
                onChange={(v) => setCampo('mensaje', v)}
              />

              {error && <p className="text-sm text-red-600">{error}</p>}

              <button
                type="submit"
                disabled={enviando || !formValido}
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

function Campo({ label, value, onChange, onBlur, error, type = 'text', tipo = 'input', placeholder, children }) {
  const baseClasses = `mt-1 w-full border rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:border-primary ${
    error ? 'border-red-400 focus:ring-red-200' : 'border-gray-300 focus:ring-primary/40'
  }`
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      {tipo === 'select' && (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          className={baseClasses}
        >
          {children}
        </select>
      )}
      {tipo === 'textarea' && (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          rows={3}
          placeholder={placeholder}
          className={`${baseClasses} resize-none`}
        />
      )}
      {tipo === 'input' && (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={placeholder}
          className={baseClasses}
        />
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </label>
  )
}