// Llamadas del panel al backend de plantillas de documentos (contrato, autorización...).
// Reutiliza `pedir` de solicitudesApi.js para las llamadas con JSON; la subida del archivo y la descarga van aparte porque usan 
// multipart y un archivo binario.
import { API_URL, ApiError } from './api.js'
import { pedir } from './solicitudesApi.js'

// Dice si el usuario puede gestionar plantillas y, si puede, entrega los servicios y las marcas:
// { puede_gestionar, max_tamano_mb, servicios: [{ id_servicio, nombre }], marcas: [{ nombre, descripcion }] }
export function obtenerConfiguracionPlantillas({ accessToken }) {
  return pedir('/api/plantillas/configuracion', { accessToken })
}

// Todas las versiones, ordenadas por servicio y de la más nueva a la más antigua:
// [{ id_plantilla, id_servicio, nombre_servicio, version, activa, fecha_creacion, nombre_original, tamano_bytes, marcas, subida_por }]
export function listarPlantillas({ accessToken }) {
  return pedir('/api/plantillas', { accessToken })
}

// Deja esta versión como la activa de su servicio (las demás quedan guardadas, inactivas).
export function activarPlantilla({ accessToken, idPlantilla }) {
  return pedir(`/api/plantillas/${idPlantilla}/activar`, { accessToken, method: 'POST' })
}

// Sube una versión nueva. El navegador arma solo el Content-Type del multipart, por eso no se define aquí.
export async function subirPlantilla({ accessToken, idServicio, archivo, activar }) {
  const formulario = new FormData()
  formulario.append('id_servicio', String(idServicio))
  formulario.append('activar', activar ? 'true' : 'false')
  formulario.append('archivo', archivo)

  const res = await fetch(`${API_URL}/api/plantillas`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formulario
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    // Los errores de negocio (marcas desconocidas, archivo repetido...) vienen como texto.
    const mensaje = typeof data?.detail === 'string' ? data.detail : 'Revisa el archivo e intenta de nuevo.'
    throw new ApiError(mensaje, res.status)
  }
  return data
}

// Descarga el archivo de una versión. Devuelve el contenido (Blob); la pantalla lo entrega al navegador.
export async function descargarPlantilla({ accessToken, idPlantilla }) {
  const res = await fetch(`${API_URL}/api/plantillas/${idPlantilla}/descargar`, {
    headers: { Authorization: `Bearer ${accessToken}` }
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(typeof data?.detail === 'string' ? data.detail : 'No se pudo descargar el archivo.', res.status)
  }
  return res.blob()
}