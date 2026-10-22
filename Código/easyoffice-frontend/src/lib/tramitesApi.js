// Llamadas del panel al listado de trámites. Reutiliza `pedir` (token Bearer, errores como ApiError) del módulo de solicitudes.
import { API_URL, ApiError } from './api.js'
import { pedir } from './solicitudesApi.js'

// Todos los filtros son opcionales: servicioId, estado, agenteId, q (texto: nombre o RUT del cliente, o código del trámite). 
// Devuelve { items, total }.
export function listarTramites({ accessToken, servicioId, estado, agenteId, q, limit, offset }) {
  const params = new URLSearchParams()
  if (servicioId) params.set('servicio_id', String(servicioId))
  if (estado) params.set('estado', estado)
  if (agenteId) params.set('agente_id', String(agenteId))
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return pedir(`/api/tramites?${params}`, { accessToken })
}

// KPIs de la cabecera y opciones de los filtros: { kpis, servicios, agentes }.
export function obtenerResumenTramites({ accessToken }) {
  return pedir('/api/tramites/resumen', { accessToken })
}

<<<<<<< Updated upstream
// --- Documento PDF del trámite (contrato, autorización...) ---

// El servidor responde `detail` como texto o, cuando faltan datos, como { mensaje, faltantes }.
function mensajeDeDocumento(data, porDefecto) {
  const detalle = data?.detail
  if (typeof detalle === 'string') return detalle
  if (typeof detalle?.mensaje === 'string') return detalle.mensaje
  return porDefecto
}

// Genera (o vuelve a generar) el PDF con la plantilla activa del servicio:
// { id_tramite, folio, nombre_archivo, tamano_bytes, hash_sha256, version_plantilla }
export async function generarDocumento({ accessToken, idTramite }) {
  const res = await fetch(`${API_URL}/api/tramites/${idTramite}/documento`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` }
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(mensajeDeDocumento(data, 'No se pudo generar el documento.'), res.status)
  return data
}

// Descarga el último PDF generado. Devuelve el contenido (Blob); la pantalla lo entrega al navegador.
export async function descargarDocumento({ accessToken, idTramite }) {
  const res = await fetch(`${API_URL}/api/tramites/${idTramite}/documento`, {
    headers: { Authorization: `Bearer ${accessToken}` }
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(mensajeDeDocumento(data, 'No se pudo descargar el documento.'), res.status)
  }
  return res.blob()
=======
// Conteos agregados para la vista de Reportes: { puede_ver, total, por_estado, por_servicio, por_agente }.
// `puede_ver` es false para quienes no son administrador (el panel muestra solo un aviso).
export function obtenerReporteTramites({ accessToken }) {
  return pedir('/api/tramites/reporte', { accessToken })
>>>>>>> Stashed changes
}