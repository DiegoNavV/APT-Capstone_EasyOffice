// Borrador del formulario del cliente. Vive SOLO en este navegador (localStorage): nunca viaja al servidor. Se guarda un único borrador 
// a la vez, asociado a un código; si entra otro código, el borrador anterior no se usa. Vence a los 7 días y el cliente puede 
// descartarlo cuando quiera. Las confirmaciones (consentimiento, "no podré editar") nunca se guardan: siempre se vuelven a marcar al enviar.

const CLAVE = 'eo_borrador_cliente'
export const DIAS_VIGENCIA = 7
const MS_POR_DIA = 24 * 60 * 60 * 1000

function hayAlgoEscrito(valores) {
  return Object.values(valores).some((v) => typeof v === 'string' && v.trim() !== '')
}

export function guardarBorrador(codigo, valores) {
  try {
    if (!hayAlgoEscrito(valores)) {
      localStorage.removeItem(CLAVE)
      return
    }
    localStorage.setItem(CLAVE, JSON.stringify({ codigo, valores, guardado: Date.now() }))
  } catch {
    // Sin almacenamiento: el formulario funciona igual, solo que sin borrador.
  }
}

// Devuelve { valores, guardado } o null si no hay borrador válido para este código.
export function leerBorrador(codigo) {
  try {
    const crudo = localStorage.getItem(CLAVE)
    if (!crudo) return null
    const dato = JSON.parse(crudo)
    if (!dato || typeof dato !== 'object' || dato.codigo !== codigo) return null
    if (typeof dato.guardado !== 'number' || Date.now() - dato.guardado > DIAS_VIGENCIA * MS_POR_DIA) {
      localStorage.removeItem(CLAVE)
      return null
    }
    if (!dato.valores || typeof dato.valores !== 'object' || Array.isArray(dato.valores)) return null
    // Solo texto: lo demás se descarta.
    const valores = Object.fromEntries(
      Object.entries(dato.valores).filter(([, v]) => typeof v === 'string')
    )
    return { valores, guardado: dato.guardado }
  } catch {
    return null
  }
}

export function descartarBorrador() {
  try {
    localStorage.removeItem(CLAVE)
  } catch {
    // Nada que descartar.
  }
}