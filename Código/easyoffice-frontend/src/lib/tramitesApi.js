// Llamadas del panel al listado de trámites. Reutiliza `pedir` (token Bearer, errores como ApiError) del módulo de solicitudes.
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