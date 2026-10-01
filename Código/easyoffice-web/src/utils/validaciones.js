// Utilidades de validación compartidas por los formularios del sitio público.

export function limpiarRut(rut) {
  return rut.replace(/[^0-9kK]/g, '').toUpperCase()
}

export function formatearRut(rut) {
  const limpio = limpiarRut(rut)
  if (limpio.length <= 1) return limpio
  const cuerpo = limpio.slice(0, -1)
  const dv = limpio.slice(-1)
  const cuerpoFormateado = cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${cuerpoFormateado}-${dv}`
}

export function validarRut(rut) {
  const limpio = limpiarRut(rut)
  if (limpio.length < 2) return false

  const cuerpo = limpio.slice(0, -1)
  const dv = limpio.slice(-1)

  if (!/^\d+$/.test(cuerpo)) return false

  let suma = 0
  let multiplo = 2
  for (let i = cuerpo.length - 1; i >= 0; i--) {
    suma += parseInt(cuerpo[i], 10) * multiplo
    multiplo = multiplo === 7 ? 2 : multiplo + 1
  }
  const resto = 11 - (suma % 11)
  const dvEsperado = resto === 11 ? '0' : resto === 10 ? 'K' : String(resto)

  return dv === dvEsperado
}

export function validarEmail(email) {
  if (!email) return false
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
}

export function validarTelefono(telefono) {
  const limpio = telefono.replace(/[^\d+]/g, '')
  // Acepta formatos chilenos: +56912345678, 912345678, 56912345678, etc.
  return /^(\+?56)?9\d{8}$/.test(limpio) || /^(\+?56)?[2-9]\d{7,8}$/.test(limpio)
}

export function validarNombre(nombre) {
  const limpio = nombre.trim()
  return limpio.length >= 3 && /^[a-zA-ZÀ-ÿ\s]+$/.test(limpio)
}

export function validarCodigoSeguimiento(codigo) {
  return /^[A-Z0-9]{8}$/.test(codigo.trim().toUpperCase())
}