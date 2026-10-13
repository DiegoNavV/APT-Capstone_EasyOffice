// Llamadas del panel al backend del módulo solicitud_contacto -> trámite.
// Reutiliza API_URL y ApiError de api.js (login), pero va en un archivo aparte para no mezclar los endpoints del login con los de las solicitudes.
import { API_URL, ApiError } from './api.js'

// FastAPI responde `detail` como texto en errores de negocio (404, 400) y como lista de objetos en errores de validación (422); 
// en ese caso no sirve como mensaje.
function mensajeDeError(data) {
  if (typeof data?.detail === 'string') return data.detail
  return 'Ocurrió un error inesperado'
}

export async function pedir(path, { accessToken, method = 'GET', body } = {}) {
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
// No se envía el responsable: el backend usa al usuario de la sesión.
// idEmpresa es opcional: si el agente eligió una empresa ya existente, el trámite queda vinculado a ella; sin idEmpresa no se manda
//  cuerpo y todo funciona como antes.
export function convertirSolicitud({ accessToken, idSolicitud, idEmpresa }) {
  return pedir(`/api/solicitudes-contacto/${idSolicitud}/convertir`, {
    accessToken,
    method: 'POST',
    body: idEmpresa ? { id_empresa: idEmpresa } : undefined
  })
}

// Empresas que el mismo solicitante ya tiene en trámites anteriores (puede venir vacío).
// Devuelve [{ id_empresa, rut_empresa, razon_social }].
export function obtenerEmpresasSugeridas({ accessToken, idSolicitud }) {
  return pedir(`/api/solicitudes-contacto/${idSolicitud}/empresas-sugeridas`, { accessToken })
}

// Buscador de empresas por razón social o RUT (el backend exige al menos 2 caracteres y devuelve como máximo 10, solo id, RUT y razón social).
export function buscarEmpresas({ accessToken, texto }) {
  const params = new URLSearchParams({ q: texto })
  return pedir(`/api/empresas?${params}`, { accessToken })
}

// Aviso "hay solicitudes nuevas": devuelve solo números ({ nuevas, ultimo_id }), nunca datos de las solicitudes. Sin desdeId 
// solo informa el id más alto.
export function obtenerNovedades({ accessToken, desdeId }) {
  const params = new URLSearchParams()
  if (desdeId !== null && desdeId !== undefined) params.set('desde_id', String(desdeId))
  const consulta = params.toString()
  return pedir(`/api/solicitudes-contacto/novedades${consulta ? `?${consulta}` : ''}`, { accessToken })
}