// Llamadas del cliente (sitio público) al backend, con su código de seguimiento.

const API_URL = import.meta.env.VITE_API_URL

export class ErrorCliente extends Error {
  constructor(mensaje, estado, errores = null) {
    super(mensaje)
    this.estado = estado
    // Errores por campo ({clave: mensaje}) cuando el servidor los informa (422).
    this.errores = errores
  }
}

const MENSAJE_SIN_CONEXION = 'No pudimos conectar con el servidor. Intenta nuevamente en unos minutos.'
const MENSAJE_LIMITE = 'Hiciste demasiados intentos en poco tiempo. Espera un minuto e inténtalo de nuevo.'
const MENSAJE_GENERICO = 'Ocurrió un error inesperado. Intenta nuevamente.'

function convertirError(estado, datos) {
  if (estado === 429) return new ErrorCliente(MENSAJE_LIMITE, 429)
  const detalle = datos?.detail
  if (typeof detalle === 'string') return new ErrorCliente(detalle, estado)
  if (detalle && typeof detalle === 'object' && !Array.isArray(detalle) && detalle.errores) {
    return new ErrorCliente(detalle.mensaje || 'Revisa los campos marcados.', estado, detalle.errores)
  }
  if (estado === 422) return new ErrorCliente('Revisa los datos e inténtalo de nuevo.', 422)
  return new ErrorCliente(MENSAJE_GENERICO, estado)
}

async function pedir(ruta, opciones = {}) {
  let respuesta
  try {
    respuesta = await fetch(`${API_URL}${ruta}`, opciones)
  } catch {
    throw new ErrorCliente(MENSAJE_SIN_CONEXION, 0)
  }
  const datos = await respuesta.json().catch(() => ({}))
  if (!respuesta.ok) throw convertirError(respuesta.status, datos)
  return datos
}

// Qué debe completar el cliente. Los datos ya registrados vienen enmascarados.
export function obtenerFormulario(codigo) {
  return pedir(`/api/tramites/codigo/${encodeURIComponent(codigo)}/formulario`)
}

// Envío ÚNICO de los datos. Devuelve solo el estado del trámite.
export function enviarDatos(codigo, cuerpo) {
  return pedir(`/api/tramites/codigo/${encodeURIComponent(codigo)}/datos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo)
  })
}