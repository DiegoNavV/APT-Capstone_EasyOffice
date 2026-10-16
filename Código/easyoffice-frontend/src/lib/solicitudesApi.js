// Llamadas del panel al backend del módulo solicitud_contacto -> trámite.
// Reutiliza API_URL y ApiError de api.js (login), pero va en un archivo aparte para no mezclar los endpoints del login con 
// los de las solicitudes.
import { API_URL, ApiError } from './api.js'

// FastAPI responde `detail` como texto en errores de negocio (404, 400) y como lista de objetos en errores de validación (422). 
// De esa lista solo sirven como mensaje los que escribimos nosotros (vienen como "Value error, <texto>"); el resto está en inglés.
function mensajeDeError(data) {
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail)) {
    const propios = data.detail
      .map((d) => (typeof d?.msg === 'string' ? d.msg : ''))
      .filter((m) => m.startsWith('Value error, '))
      .map((m) => m.slice('Value error, '.length))
    if (propios.length > 0) return [...new Set(propios)].join(' ')
    return 'Revisa los datos ingresados.'
  }
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
// Todo lo demás es opcional: idEmpresa vincula una empresa ya existente; idSucursal asigna sucursal y folio; condiciones (servicios, 
// precios, ciclos, duración y fechas) exige sucursal.
// Sin nada de eso no se manda cuerpo y todo funciona como antes.
export function convertirSolicitud({ accessToken, idSolicitud, idEmpresa, idSucursal, condiciones }) {
  const body = {
    ...(idEmpresa ? { id_empresa: idEmpresa } : {}),
    ...(idSucursal ? { id_sucursal: idSucursal } : {}),
    ...(condiciones ? { condiciones } : {})
  }
  return pedir(`/api/solicitudes-contacto/${idSolicitud}/convertir`, {
    accessToken,
    method: 'POST',
    body: Object.keys(body).length > 0 ? body : undefined
  })
}

// Catálogos para armar el contrato (requieren login).
// Sucursales activas: [{ id_sucursal, iniciales, nombre, direccion, comuna, region, rol_propiedad }]
export function obtenerSucursales({ accessToken }) {
  return pedir('/api/sucursales', { accessToken })
}

// Servicios que vende Easy Office: [{ id_servicio_ofrecido, nombre, descripcion, precio_referencia, ciclo_pago_defecto }]
export function obtenerServiciosOfrecidos({ accessToken }) {
  return pedir('/api/servicios-ofrecidos', { accessToken })
}

// Valores permitidos: { ciclos_pago, duraciones_meses, max_servicios }
export function obtenerOpcionesContrato({ accessToken }) {
  return pedir('/api/opciones-contrato', { accessToken })
}

// Empresas que el mismo solicitante ya tiene en trámites anteriores (puede venir vacío).
// Devuelve [{ id_empresa, rut_empresa, razon_social }].
export function obtenerEmpresasSugeridas({ accessToken, idSolicitud }) {
  return pedir(`/api/solicitudes-contacto/${idSolicitud}/empresas-sugeridas`, { accessToken })
}

// Buscador de empresas por razón social o RUT (el backend exige al menos 2 caracteres
// y devuelve como máximo 10, solo id, RUT y razón social).
export function buscarEmpresas({ accessToken, texto }) {
  const params = new URLSearchParams({ q: texto })
  return pedir(`/api/empresas?${params}`, { accessToken })
}

// Aviso "hay solicitudes nuevas": devuelve solo números ({ nuevas, ultimo_id }),
// nunca datos de las solicitudes. Sin desdeId solo informa el id más alto.
export function obtenerNovedades({ accessToken, desdeId }) {
  const params = new URLSearchParams()
  if (desdeId !== null && desdeId !== undefined) params.set('desde_id', String(desdeId))
  const consulta = params.toString()
  return pedir(`/api/solicitudes-contacto/novedades${consulta ? `?${consulta}` : ''}`, { accessToken })
}