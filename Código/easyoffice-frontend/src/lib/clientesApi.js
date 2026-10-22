// Llamadas del panel al listado de clientes. Reutiliza `pedir` (token Bearer, errores como ApiError) del módulo de solicitudes.
import { pedir } from './solicitudesApi.js'

// Filtro opcional q (nombre o RUT). Devuelve { items, total }.
export function listarClientes({ accessToken, q, limit, offset }) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return pedir(`/api/clientes?${params}`, { accessToken })
}

// Ficha de cliente 360°: datos de contacto, empresas vinculadas y el historial completo de sus trámites.
export function obtenerCliente({ accessToken, idCliente }) {
  return pedir(`/api/clientes/${idCliente}`, { accessToken })
}
