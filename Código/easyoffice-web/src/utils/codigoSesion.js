import { validarCodigoSeguimiento } from './validaciones.js'

// El código de seguimiento es la única credencial del cliente. No se deja en la URL (historial, marcadores, enlaces compartidos, 
// registros del servidor web): se guarda en sessionStorage, que vive solo mientras la pestaña está abierta.
// Si el navegador bloquea el almacenamiento (modo privado), se usa memoria: la navegación dentro del sitio sigue funcionando, 
// solo se pierde al recargar.

const CLAVE = 'eo_codigo_seguimiento'
let enMemoria = ''

export function guardarCodigo(codigo) {
  enMemoria = codigo
  try {
    sessionStorage.setItem(CLAVE, codigo)
  } catch {
    // Sin almacenamiento: queda solo en memoria.
  }
}

export function leerCodigo() {
  let guardado = ''
  try {
    guardado = sessionStorage.getItem(CLAVE) ?? ''
  } catch {
    // Sin almacenamiento: se usa la memoria.
  }
  const codigo = (guardado || enMemoria).toUpperCase()
  return validarCodigoSeguimiento(codigo) ? codigo : ''
}

export function borrarCodigo() {
  enMemoria = ''
  try {
    sessionStorage.removeItem(CLAVE)
  } catch {
    // Nada que borrar.
  }
}