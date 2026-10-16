import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../lib/api.js'
import {
  obtenerOpcionesContrato,
  obtenerServiciosOfrecidos,
  obtenerSucursales
} from '../lib/solicitudesApi.js'
import {
  calcularVencimiento,
  evaluarContrato,
  formatearFechaIso,
  OPCIONES_RESPALDO
} from '../lib/condicionesContrato.js'

// Paso del agente al convertir: sucursal (que da el folio y los datos del local) y, para el contrato de servicio, las condiciones: servicios 
// con su precio y ciclo de pago, duración, fecha de inicio y vencimiento. Para la autorización de domicilio tributario solo se pide
// la sucursal (`soloSucursal`). Nada se preselecciona: lo decide el agente.
// Cada cambio se informa al padre con `onCambio({ error, idSucursal, condiciones })`; mientras `error` no esté vacío, el padre no 
// deja convertir.

const CLASE_CAMPO =
  'mt-1 w-full text-sm text-ink-primary bg-surface border border-line-strong rounded-[10px] px-3 py-2 focus:outline-none focus:border-brand-primary disabled:opacity-60'

const formatoPeso = new Intl.NumberFormat('es-CL')

function etiquetaDuracion(meses) {
  return meses === 1 ? '1 mes' : `${meses} meses`
}

let contadorFilas = 0
const filaVacia = () => ({ clave: (contadorFilas += 1), id: '', precio: '', ciclo: '' })

export default function CondicionesContrato({
  idSolicitud,
  accessToken,
  soloSucursal = false,
  onSesionVencida,
  onCambio,
  deshabilitado = false
}) {
  const [sucursales, setSucursales] = useState([])
  const [servicios, setServicios] = useState([])
  const [opciones, setOpciones] = useState(OPCIONES_RESPALDO)
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState('')
  const [reintento, setReintento] = useState(0)

  const [idSucursal, setIdSucursal] = useState('')
  const [filas, setFilas] = useState(() => [filaVacia()])
  const [duracion, setDuracion] = useState('12')
  const [inicio, setInicio] = useState('')
  // Vencimiento escrito a mano por el agente ('' = se usa el calculado).
  const [vencimientoManual, setVencimientoManual] = useState('')

  useEffect(() => {
    let cancelado = false
    setCargando(true)
    setErrorCarga('')
    const pedidos = soloSucursal
      ? [obtenerSucursales({ accessToken })]
      : [
          obtenerSucursales({ accessToken }),
          obtenerServiciosOfrecidos({ accessToken }),
          obtenerOpcionesContrato({ accessToken })
        ]
    Promise.all(pedidos)
      .then(([suc, serv, opc]) => {
        if (cancelado) return
        setSucursales(suc)
        if (serv) setServicios(serv)
        if (opc) setOpciones(opc)
      })
      .catch((e) => {
        if (cancelado) return
        if (e instanceof ApiError && e.status === 401) {
          onSesionVencida?.()
          return
        }
        setErrorCarga(e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.')
      })
      .finally(() => {
        if (!cancelado) setCargando(false)
      })
    return () => {
      cancelado = true
    }
    // El token se renueva solo; los catálogos se piden una vez al abrir el paso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soloSucursal, reintento])

  const vencimientoCalculado = useMemo(
    () => calcularVencimiento(inicio, Number(duracion)),
    [inicio, duracion]
  )
  const vencimientoEfectivo = vencimientoManual || vencimientoCalculado

  // Informa al padre qué se puede enviar (o qué falta).
  useEffect(() => {
    if (cargando) {
      onCambio({ error: 'Cargando las opciones del contrato…', idSucursal: null, condiciones: null })
    } else if (errorCarga) {
      onCambio({ error: 'No se pudieron cargar las opciones del contrato.', idSucursal: null, condiciones: null })
    } else {
      onCambio(
        evaluarContrato({
          soloSucursal,
          idSucursal,
          filas,
          duracion,
          inicio,
          vencimiento: vencimientoManual
        })
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargando, errorCarga, soloSucursal, idSucursal, filas, duracion, inicio, vencimientoManual])

  function cambiarFila(clave, cambios) {
    setFilas((prev) => prev.map((f) => (f.clave === clave ? { ...f, ...cambios } : f)))
  }

  // Al elegir un servicio se proponen su precio y ciclo de referencia; el agente los ajusta.
  function elegirServicio(clave, id) {
    const servicio = servicios.find((s) => String(s.id_servicio_ofrecido) === id)
    cambiarFila(clave, {
      id,
      precio: servicio?.precio_referencia != null ? String(servicio.precio_referencia) : '',
      ciclo: servicio?.ciclo_pago_defecto || ''
    })
  }

  function cambiarVencimiento(valor) {
    // Si vuelve a coincidir con el calculado, deja de contar como corrección manual.
    setVencimientoManual(valor === vencimientoCalculado ? '' : valor)
  }

  const idp = `contrato-${idSolicitud}`
  const maxServicios = opciones.max_servicios
  const sucursalElegida = sucursales.find((s) => String(s.id_sucursal) === idSucursal)

  if (cargando) {
    return <p className="mt-4 text-xs text-ink-muted">Cargando las opciones del contrato…</p>
  }

  if (errorCarga) {
    return (
      <div role="alert" className="mt-4 text-sm text-red-600">
        {errorCarga}{' '}
        <button
          type="button"
          onClick={() => setReintento((n) => n + 1)}
          className="font-medium text-ink-link hover:underline"
        >
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <fieldset className="mt-4" disabled={deshabilitado}>
      <legend className="text-sm font-semibold text-ink-primary">
        {soloSucursal ? 'Sucursal' : 'Sucursal y condiciones del contrato'}
      </legend>

      <div className="mt-2">
        <label htmlFor={`${idp}-sucursal`} className="text-xs text-ink-muted">
          Sucursal donde se firma
        </label>
        <select
          id={`${idp}-sucursal`}
          value={idSucursal}
          onChange={(e) => setIdSucursal(e.target.value)}
          className={CLASE_CAMPO}
        >
          <option value="">Elige una sucursal…</option>
          {sucursales.map((s) => (
            <option key={s.id_sucursal} value={s.id_sucursal}>
              {s.nombre} ({s.iniciales})
            </option>
          ))}
        </select>
        {sucursalElegida && (
          <p className="mt-1 text-xs text-ink-muted">
            {sucursalElegida.direccion}, {sucursalElegida.comuna}. Se asignará un folio{' '}
            {sucursalElegida.iniciales}-NN-{new Date().getFullYear()} automáticamente.
          </p>
        )}
      </div>

      {!soloSucursal && (
        <>
          <div className="mt-4 space-y-3">
            {filas.map((fila, indice) => {
              const usados = filas.filter((f) => f.clave !== fila.clave).map((f) => f.id)
              return (
                <div key={fila.clave} className="rounded-[10px] border border-line p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-ink-primary">Servicio {indice + 1}</p>
                    {filas.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setFilas((prev) => prev.filter((f) => f.clave !== fila.clave))}
                        className="text-xs font-medium text-ink-secondary hover:underline"
                      >
                        Quitar
                      </button>
                    )}
                  </div>

                  <label htmlFor={`${idp}-serv-${fila.clave}`} className="mt-2 block text-xs text-ink-muted">
                    Servicio
                  </label>
                  <select
                    id={`${idp}-serv-${fila.clave}`}
                    value={fila.id}
                    onChange={(e) => elegirServicio(fila.clave, e.target.value)}
                    className={CLASE_CAMPO}
                  >
                    <option value="">Elige un servicio…</option>
                    {servicios
                      .filter((s) => !usados.includes(String(s.id_servicio_ofrecido)))
                      .map((s) => (
                        <option key={s.id_servicio_ofrecido} value={s.id_servicio_ofrecido}>
                          {s.nombre}
                        </option>
                      ))}
                  </select>

                  <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label htmlFor={`${idp}-precio-${fila.clave}`} className="text-xs text-ink-muted">
                        Precio (CLP)
                      </label>
                      <input
                        id={`${idp}-precio-${fila.clave}`}
                        type="text"
                        inputMode="numeric"
                        value={fila.precio}
                        onChange={(e) => cambiarFila(fila.clave, { precio: e.target.value.replace(/\D/g, '').slice(0, 9) })}
                        placeholder="Ej: 59990"
                        className={CLASE_CAMPO}
                      />
                      {fila.precio !== '' && (
                        <p className="mt-1 text-xs text-ink-muted">${formatoPeso.format(Number(fila.precio))}</p>
                      )}
                    </div>
                    <div>
                      <label htmlFor={`${idp}-ciclo-${fila.clave}`} className="text-xs text-ink-muted">
                        Ciclo de pago
                      </label>
                      <select
                        id={`${idp}-ciclo-${fila.clave}`}
                        value={fila.ciclo}
                        onChange={(e) => cambiarFila(fila.clave, { ciclo: e.target.value })}
                        className={CLASE_CAMPO}
                      >
                        <option value="">Elige un ciclo…</option>
                        {opciones.ciclos_pago.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              )
            })}

            {filas.length < maxServicios && (
              <button
                type="button"
                onClick={() => setFilas((prev) => [...prev, filaVacia()])}
                className="text-sm font-medium text-ink-link hover:underline"
              >
                + Agregar otro servicio (máximo {maxServicios})
              </button>
            )}
          </div>

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label htmlFor={`${idp}-duracion`} className="text-xs text-ink-muted">
                Duración
              </label>
              <select
                id={`${idp}-duracion`}
                value={duracion}
                onChange={(e) => setDuracion(e.target.value)}
                className={CLASE_CAMPO}
              >
                {opciones.duraciones_meses.map((m) => (
                  <option key={m} value={m}>
                    {etiquetaDuracion(m)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`${idp}-inicio`} className="text-xs text-ink-muted">
                Fecha de inicio
              </label>
              <input
                id={`${idp}-inicio`}
                type="date"
                value={inicio}
                min="2020-01-01"
                max="2100-12-31"
                onChange={(e) => setInicio(e.target.value)}
                className={CLASE_CAMPO}
              />
            </div>
            <div>
              <label htmlFor={`${idp}-vencimiento`} className="text-xs text-ink-muted">
                Vencimiento
              </label>
              <input
                id={`${idp}-vencimiento`}
                type="date"
                value={vencimientoEfectivo}
                min="2020-01-01"
                max="2100-12-31"
                onChange={(e) => cambiarVencimiento(e.target.value)}
                className={CLASE_CAMPO}
              />
            </div>
          </div>

          <p className="mt-2 text-xs text-ink-muted">
            {vencimientoManual ? (
              <>
                Corregiste el vencimiento a mano (el sistema proponía {formatearFechaIso(vencimientoCalculado)}).{' '}
                <button
                  type="button"
                  onClick={() => setVencimientoManual('')}
                  className="font-medium text-ink-link hover:underline"
                >
                  Volver al calculado
                </button>
              </>
            ) : (
              'El vencimiento se calcula solo (inicio + duración − 1 día). Revísalo: no considera feriados ni días hábiles, y puedes corregirlo.'
            )}
          </p>
        </>
      )}
    </fieldset>
  )
}