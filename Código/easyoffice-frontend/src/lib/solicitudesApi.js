// Llamadas del panel al backend del módulo solicitud_contacto -> trámite.
// Reutiliza API_URL y ApiError de api.js (login), pero va en un archivo aparte
// para no mezclar los endpoints del login con los de las solicitudes.
import { API_URL, ApiError } from './api.js'

// FastAPI responde `detail` como texto en errores de negocio (404, 400) y como
// lista de objetos en errores de validación (422); en ese caso no sirve como mensaje.
function mensajeDeError(data) {
  if (typeof data?.detail === 'string') return data.detail
  return 'Ocurrió un error inesperado'
}

async function pedir(path, { accessToken, method = 'GET', body } = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(body ? { 'Content-Type': 'application/json' } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new ApiError(mensajeDeError(data), res.status)
  }
  return data
}

// estado: '' (todas) | 'pendiente' | 'convertido'
export function listarSolicitudes({ accessToken, estado, limit, offset }) {
  const params = new URLSearchParams()
  if (estado) params.set('estado', estado)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return pedir(`/api/solicitudes-contacto?${params}`, { accessToken })
}

// Confirma el pago manual y convierte la solicitud en trámite (genera el código).
export function convertirSolicitud({ accessToken, idSolicitud, idUsuarioResponsable }) {
  return pedir(`/api/solicitudes-contacto/${idSolicitud}/convertir`, {
    accessToken,
    method: 'POST',
    body: { id_usuario_responsable: idUsuarioResponsable }
  })
}