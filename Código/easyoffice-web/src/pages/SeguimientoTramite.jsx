import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import { validarCodigoSeguimiento } from '../utils/validaciones.js'
import { guardarCodigo, leerCodigo } from '../utils/codigoSesion.js'

// Estados posibles (catálogo estado_tramite): esperando_datos, procesando_firma, en_revision (solo caso B), firmado, entregado, cancelado, rechazado.
// "esperando_datos" es el estado inicial: el código ya existe y falta que el cliente complete sus datos.
const ESTADOS_LABEL = {
  esperando_datos: 'Esperando tus datos',
  procesando_firma: 'Procesando firma',
  en_revision: 'En revisión',
  firmado: 'Firmado',
  entregado: 'Entregado',
  cancelado: 'Cancelado',
  rechazado: 'Rechazado'
}

// Qué le decimos al cliente mientras su documento no está listo para descargar.
const MENSAJE_POR_ESTADO = {
  procesando_firma: 'Estamos procesando la firma de tu documento. Vuelve a consultar en unos minutos con el mismo código.',
  en_revision: 'Un agente está revisando tus datos. Vuelve a consultar más tarde con el mismo código.',
  rechazado: 'No se pudo completar la firma de tu documento. Contacta a tu agente indicando tu código.',
  cancelado: 'Este trámite fue cancelado. Si crees que es un error, contacta a tu agente indicando tu código.'
}
const MENSAJE_POR_DEFECTO = 'Tu documento aún se está procesando. Vuelve a consultar más tarde con el mismo código.'

// El servidor manda el nombre en la cabecera Content-Disposition. Con acentos o ñ viene en el formato
// filename*=utf-8''Nombre%20codificado.pdf; sin ellos, como filename="Nombre.pdf". Si no se puede leer, uno genérico.
function nombreDeArchivo(respuesta) {
  const cabecera = respuesta.headers.get('content-disposition') || ''

  const codificado = cabecera.match(/filename\*=utf-8''([^;]+)/i)
  if (codificado) {
    try {
      return decodeURIComponent(codificado[1].trim())
    } catch {
      // Codificación inválida: se prueba con el formato simple.
    }
  }

  const simple = cabecera.match(/filename="?([^";]+)"?/i)
  return simple ? simple[1].trim() : 'documento-firmado.pdf'
}

export default function SeguimientoTramite() {
  // El código no viaja en la URL: se toma de la sesión de esta pestaña (ver utils/codigoSesion.js).
  const [codigo, setCodigo] = useState(() => leerCodigo())
  const [buscando, setBuscando] = useState(false)
  const [tramite, setTramite] = useState(null)
  const [error, setError] = useState(null)
  const [descargando, setDescargando] = useState(false)
  const [errorDescarga, setErrorDescarga] = useState(null)
  const [descargado, setDescargado] = useState(false)
  const { key } = useLocation()
  const ultimaClave = useRef(null)

  const codigoValido = validarCodigoSeguimiento(codigo)

  function onCambiarCodigo(valor) {
    const limpio = valor.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8)
    setCodigo(limpio)
  }

  async function consultarCodigo(codigoAConsultar) {
    setBuscando(true)
    setError(null)
    setTramite(null)
    setErrorDescarga(null)
    setDescargado(false)
    try {
      const respuesta = await fetch(
        `${import.meta.env.VITE_API_URL}/api/tramites/codigo/${encodeURIComponent(codigoAConsultar)}`
      )

      if (respuesta.status === 429) {
        setError('Hiciste demasiados intentos en poco tiempo. Espera un minuto e inténtalo de nuevo.')
        return
      }
      if (!respuesta.ok) {
        throw new Error('No encontrado')
      }

      const datos = await respuesta.json()
      guardarCodigo(codigoAConsultar)
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

  // Descarga el documento firmado desde nuestro servidor (nunca desde la API de firma). La primera descarga
  // deja el trámite como "Entregado"; por eso se actualiza el estado que se muestra.
  async function descargarDocumento() {
    setDescargando(true)
    setErrorDescarga(null)
    setDescargado(false)
    try {
      const respuesta = await fetch(
        `${import.meta.env.VITE_API_URL}/api/tramites/codigo/${encodeURIComponent(tramite.codigo_seguimiento)}/documento`
      )

      if (respuesta.status === 429) {
        setErrorDescarga('Hiciste demasiados intentos en poco tiempo. Espera un minuto e inténtalo de nuevo.')
        return
      }
      if (!respuesta.ok) {
        let mensaje = 'No pudimos descargar tu documento. Inténtalo de nuevo más tarde.'
        try {
          const cuerpo = await respuesta.json()
          if (typeof cuerpo.detail === 'string') mensaje = cuerpo.detail
        } catch {
          // El servidor no devolvió un mensaje legible: se usa el genérico.
        }
        setErrorDescarga(mensaje)
        return
      }

      const nombre = nombreDeArchivo(respuesta)
      const blob = await respuesta.blob()
      const url = URL.createObjectURL(blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = nombre
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      URL.revokeObjectURL(url)

      setDescargado(true)
      setTramite((actual) =>
        actual && actual.estado_actual === 'firmado' ? { ...actual, estado_actual: 'entregado' } : actual
      )
    } catch {
      setErrorDescarga('No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.')
    } finally {
      setDescargando(false)
    }
  }

  // Cada vez que se llega a esta vista (al abrir la página o al ingresar un código desde la ventana del botón
  // "Inicia tu trámite" estando ya aquí) se lee el código guardado en la sesión y se consulta de inmediato.
  // `ultimaClave` evita consultar dos veces en la misma visita (el modo estricto de React ejecuta el efecto doble).
  useEffect(() => {
    if (ultimaClave.current === key) return
    ultimaClave.current = key
    const guardado = leerCodigo()
    if (validarCodigoSeguimiento(guardado)) {
      setCodigo(guardado)
      consultarCodigo(guardado.trim().toUpperCase())
    }
  }, [key])

  function consultar(e) {
    e.preventDefault()
    if (!codigoValido) {
      setError('El código debe tener 8 caracteres (letras y números).')
      return
    }
    consultarCodigo(codigo)
  }

  const faltanDatos = tramite?.estado_actual === 'esperando_datos'

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

              {faltanDatos ? (
                <>
                  <p className="mt-6 text-sm text-gray-600">
                    Para avanzar con tu trámite necesitamos que completes algunos datos.
                  </p>
                  <Link
                    to="/completar-datos"
                    className="mt-4 block w-full text-center bg-primary hover:bg-primary-dark text-white font-semibold py-3 rounded-lg transition-colors"
                  >
                    Completar mis datos
                  </Link>
                </>
              ) : tramite.documento_disponible ? (
                <>
                  <button
                    type="button"
                    onClick={descargarDocumento}
                    disabled={descargando}
                    className="mt-6 w-full bg-accent hover:bg-amber-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors"
                  >
                    {descargando ? 'Descargando...' : 'Descargar documento firmado'}
                  </button>
                  {errorDescarga && (
                    <p role="alert" className="mt-3 text-sm text-red-600">
                      {errorDescarga}
                    </p>
                  )}
                  {descargado && (
                    <p role="status" className="mt-3 text-sm text-green-700">
                      Tu documento se descargó correctamente. Puedes volver a descargarlo cuando quieras con tu código.
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-6 text-sm text-gray-600">
                  {MENSAJE_POR_ESTADO[tramite.estado_actual] ?? MENSAJE_POR_DEFECTO}
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