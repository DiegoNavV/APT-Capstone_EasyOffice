import { formatearRut, validarEmail, validarRut } from './validaciones.js'

// Reglas del formulario del cliente. Son una ayuda para que corrija antes de enviar; la validación definitiva la hace 
// siempre el servidor (que informa los errores de cada campo y se muestran junto al campo).

export function camposPendientes(campos) {
  return campos.filter((c) => !c.registrado)
}

function soloDigitosCelular(valor) {
  const digitos = valor.replace(/\D/g, '')
  return digitos.length === 11 && digitos.startsWith('56') ? digitos.slice(2) : digitos
}

function esFechaValida(valor) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(valor)
  if (!m) return false
  const [, a, mes, d] = m.map(Number)
  const fecha = new Date(Date.UTC(a, mes - 1, d))
  const coincide = fecha.getUTCFullYear() === a && fecha.getUTCMonth() === mes - 1 && fecha.getUTCDate() === d
  const hoy = new Date()
  const hoyUtc = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
  return coincide && a >= 1900 && fecha.getTime() <= hoyUtc
}

// Devuelve el mensaje de error o null si el valor está bien.
export function validarCampo(campo, valor) {
  const v = (valor ?? '').trim()
  if (!v) return 'Este campo es obligatorio.'
  if (v.length > campo.max_largo) return `Máximo ${campo.max_largo} caracteres.`
  switch (campo.tipo) {
    case 'rut':
      return validarRut(v) ? null : 'El RUT ingresado no es válido.'
    case 'email':
      return validarEmail(v) ? null : 'Ingresa un correo electrónico válido.'
    case 'celular':
      return /^9\d{8}$/.test(soloDigitosCelular(v))
        ? null
        : 'Ingresa un celular de 9 dígitos que parta con 9. Ejemplo: 9 1234 5678.'
    case 'fecha':
      return esFechaValida(v) ? null : 'Ingresa una fecha válida (no puede ser futura).'
    default:
      return null
  }
}

// Errores {clave: mensaje} solo de los campos que el cliente debe completar.
export function validarFormulario(campos, valores) {
  const errores = {}
  for (const campo of camposPendientes(campos)) {
    const error = validarCampo(campo, valores[campo.clave])
    if (error) errores[campo.clave] = error
  }
  return errores
}

// Lo que se escribe en el campo mientras el cliente tipea.
export function normalizarEntrada(campo, valor) {
  if (campo.tipo === 'rut') return formatearRut(valor).slice(0, campo.max_largo)
  if (campo.tipo === 'celular') return valor.replace(/[^\d+\s]/g, '').slice(0, campo.max_largo)
  return valor.slice(0, campo.max_largo)
}

// Atributos del <input> según el tipo de dato.
export function atributosInput(tipo) {
  switch (tipo) {
    case 'rut':
      return { type: 'text', placeholder: '12.345.678-9', autoComplete: 'off' }
    case 'email':
      return { type: 'email', placeholder: 'nombre@empresa.cl', autoComplete: 'off' }
    case 'celular':
      return { type: 'tel', placeholder: '9 1234 5678', autoComplete: 'off' }
    case 'fecha':
      return { type: 'date', placeholder: '', autoComplete: 'off' }
    default:
      return { type: 'text', placeholder: '', autoComplete: 'off' }
  }
}

// Cómo se ve cada valor en el resumen previo al envío.
export function formatearParaResumen(campo, valor) {
  const v = (valor ?? '').trim()
  if (campo.tipo === 'rut') return formatearRut(v)
  if (campo.tipo === 'celular') {
    const d = soloDigitosCelular(v)
    return d.length === 9 ? `${d[0]} ${d.slice(1, 5)} ${d.slice(5)}` : v
  }
  if (campo.tipo === 'fecha') {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v)
    return m ? `${m[3]}-${m[2]}-${m[1]}` : v
  }
  return v
}

// Solo lo que se envía: los campos pendientes, con el texto recortado.
export function valoresParaEnviar(campos, valores) {
  return Object.fromEntries(
    camposPendientes(campos).map((c) => [c.clave, (valores[c.clave] ?? '').trim()])
  )
}