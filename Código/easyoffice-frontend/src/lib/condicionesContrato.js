// Reglas del formulario de condiciones del contrato (lado panel). El backend vuelve a validar todo; esto solo evita que el agente 
// pierda tiempo con errores evidentes y calcula la fecha de vencimiento que se propone.

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/
export const PRECIO_MAXIMO = 100000000
const ANIO_MIN = 2020
const ANIO_MAX = 2100

// Mismos valores de partida que entrega GET /api/opciones-contrato (el panel usa los reales del servidor; estos solo existen para 
// no dejar el formulario vacío si esa llamada falla).
export const OPCIONES_RESPALDO = {
  ciclos_pago: ['ÚNICO', 'ANUAL', 'SEMESTRAL', 'TRIMESTRAL', 'MENSUAL'],
  duraciones_meses: [12, 6, 4, 3, 1],
  max_servicios: 3
}

export function fechaValida(iso) {
  const m = ISO.exec(iso || '')
  if (!m) return false
  const [anio, mes, dia] = [Number(m[1]), Number(m[2]), Number(m[3])]
  if (anio < ANIO_MIN || anio > ANIO_MAX) return false
  const f = new Date(Date.UTC(anio, mes - 1, dia))
  return f.getUTCFullYear() === anio && f.getUTCMonth() === mes - 1 && f.getUTCDate() === dia
}

function aIso(anio, mes0, dia) {
  return new Date(Date.UTC(anio, mes0, dia)).toISOString().slice(0, 10)
}

// Mismo criterio que el backend (condiciones.calcular_vencimiento): mismo día N meses después, menos un día; si ese día no existe en el 
// mes de destino, el último día del mes.
// 2026-01-15 + 12 -> 2027-01-14 | 2026-01-31 + 1 -> 2026-02-28.
// Es solo una propuesta: no considera feriados ni días hábiles.
export function calcularVencimiento(inicioIso, meses) {
  if (!fechaValida(inicioIso) || !Number.isInteger(meses) || meses < 1) return ''
  const [, a, m, d] = ISO.exec(inicioIso).map(Number)
  const indice = m - 1 + meses
  const anio = a + Math.floor(indice / 12)
  const mes0 = indice % 12
  const ultimo = new Date(Date.UTC(anio, mes0 + 1, 0)).getUTCDate()
  const dia = Math.min(d, ultimo)
  return dia !== d ? aIso(anio, mes0, dia) : aIso(anio, mes0, dia - 1)
}

export function formatearFechaIso(iso) {
  const m = ISO.exec(iso || '')
  return m ? `${m[3]}-${m[2]}-${m[1]}` : ''
}

// Devuelve lo que necesita el botón de convertir:
//   { error: '' | 'qué falta', idSucursal: number | null, condiciones: objeto del backend | null }
// `filas` = [{ id: '', precio: '', ciclo: '' }] con valores de formulario (texto).
export function evaluarContrato({ soloSucursal, idSucursal, filas, duracion, inicio, vencimiento }) {
  const sucursal = Number(idSucursal)
  if (!idSucursal || !Number.isInteger(sucursal)) {
    return { error: 'Elige la sucursal.', idSucursal: null, condiciones: null }
  }
  if (soloSucursal) return { error: '', idSucursal: sucursal, condiciones: null }

  const resultado = (error) => ({ error, idSucursal: sucursal, condiciones: null })

  if (filas.length === 0) return resultado('Agrega al menos un servicio.')
  const servicios = []
  for (let i = 0; i < filas.length; i += 1) {
    const f = filas[i]
    const n = i + 1
    if (!f.id) return resultado(`Elige el servicio ${n}.`)
    if (!/^\d+$/.test(String(f.precio))) return resultado(`Indica el precio del servicio ${n} (solo números, 0 si no tiene costo).`)
    const precio = Number(f.precio)
    if (precio > PRECIO_MAXIMO) return resultado(`El precio del servicio ${n} es demasiado alto.`)
    if (!f.ciclo) return resultado(`Elige el ciclo de pago del servicio ${n}.`)
    servicios.push({ id_servicio_ofrecido: Number(f.id), precio, ciclo_pago: f.ciclo })
  }

  if (!fechaValida(inicio)) return resultado('Indica una fecha de inicio válida.')
  const meses = Number(duracion)
  const calculado = calcularVencimiento(inicio, meses)
  const efectivo = vencimiento || calculado
  if (!fechaValida(efectivo)) return resultado('Indica una fecha de vencimiento válida.')
  if (efectivo <= inicio) return resultado('El vencimiento debe ser posterior a la fecha de inicio.')

  const condiciones = {
    servicios,
    duracion_meses: meses,
    fecha_inicio: inicio,
    // Solo se manda si el agente la corrigió; si no, el servidor calcula la misma.
    ...(vencimiento && vencimiento !== calculado ? { fecha_vencimiento: vencimiento } : {})
  }
  return { error: '', idSucursal: sucursal, condiciones }
}