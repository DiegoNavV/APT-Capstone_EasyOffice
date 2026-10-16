import { useEffect, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import { convertirSolicitud, listarSolicitudes } from '../lib/solicitudesApi.js'
import { useNovedadesSolicitudes } from '../lib/useNovedadesSolicitudes.js'
import PaginaPanel from '../components/PaginaPanel.jsx'
import CondicionesContrato from '../components/CondicionesContrato.jsx'
import SelectorEmpresa, { textoEmpresa } from '../components/SelectorEmpresa.jsx'

// Solicitudes que llegan desde el formulario "Contrata aquí" del sitio público.
// El agente/admin confirma el pago manual y la convierte en trámite: ahí se genera el código de 8 caracteres que luego le entrega al cliente.

const POR_PAGINA = 10

const FILTROS = [
  { valor: '', texto: 'Todas' },
  { valor: 'pendiente', texto: 'Pendientes' },
  { valor: 'convertido', texto: 'Convertidas' }
]

function formatearFecha(iso) {
  if (!iso) return '—'
  // El backend guarda la fecha en UTC pero la devuelve sin zona horaria "2026-10-08T19:42:11"); sin la "Z" el navegador 
  // la tomaría como hora local.
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`
  const fecha = new Date(conZona)
  if (Number.isNaN(fecha.getTime())) return '—'
  return fecha.toLocaleString('es-CL', { dateStyle: 'short', timeStyle: 'short' })
}

function Dato({ etiqueta, valor }) {
  return (
    <div>
      <dt className="text-xs text-ink-muted">{etiqueta}</dt>
      <dd className="text-sm text-ink-primary break-words">{valor || '—'}</dd>
    </div>
  )
}

// La autorización de domicilio tributario solo necesita la sucursal; el contrato de servicio (y cualquier otro servicio) pide además 
// las condiciones. Se decide por el nombre del servicio de interés que ya trae la solicitud.
function soloPideSucursal(nombreServicio) {
  return /autorizaci[oó]n/i.test(nombreServicio || '')
}

const CONTRATO_PENDIENTE = { error: 'Cargando las opciones del contrato…', idSucursal: null, condiciones: null }

function TarjetaSolicitud({ solicitud, accessToken, onConvertir, onSesionVencida }) {
  const [confirmando, setConfirmando] = useState(false)
  // Empresa existente a la que el agente decide vincular el trámite (null = sin empresa).
  const [empresa, setEmpresa] = useState(null)
  // Sucursal y condiciones que arma CondicionesContrato (error != '' = todavía no se puede convertir).
  const [contrato, setContrato] = useState(CONTRATO_PENDIENTE)
  const [convirtiendo, setConvirtiendo] = useState(false)
  const [errorConversion, setErrorConversion] = useState('')
  const [copiado, setCopiado] = useState(false)

  const convertida = solicitud.estado === 'convertido'
  const sinServicio = !solicitud.id_servicio

  async function confirmar() {
    setConvirtiendo(true)
    setErrorConversion('')
    try {
      await onConvertir(solicitud, {
        idEmpresa: empresa?.id_empresa,
        idSucursal: contrato.idSucursal,
        condiciones: contrato.condiciones
      })
      setConfirmando(false)
    } catch (e) {
      setErrorConversion(e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.')
    } finally {
      setConvirtiendo(false)
    }
  }

  async function copiarCodigo() {
    try {
      await navigator.clipboard.writeText(solicitud.codigo_seguimiento)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      // Sin permiso de portapapeles: el código igual queda a la vista para copiarlo a mano.
    }
  }

  return (
    <article className="bg-surface border border-line rounded-2xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-ink-primary">{solicitud.nombre}</h2>
          <p className="text-xs text-ink-muted">Recibida el {formatearFecha(solicitud.fecha_creacion)}</p>
        </div>
        <span
          className={`text-xs font-medium px-2.5 py-1 rounded-full ${
            convertida ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
          }`}
        >
          {convertida ? 'Convertida' : 'Pendiente'}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
        <Dato etiqueta="RUT" valor={solicitud.rut} />
        <Dato etiqueta="Servicio de interés" valor={solicitud.nombre_servicio} />
        <Dato etiqueta="Email" valor={solicitud.email} />
        <Dato etiqueta="Teléfono" valor={solicitud.telefono} />
      </dl>

      {solicitud.mensaje && (
        <div className="mt-3">
          <p className="text-xs text-ink-muted">Mensaje</p>
          <p className="text-sm text-ink-secondary whitespace-pre-line break-words">{solicitud.mensaje}</p>
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-line">
        {convertida ? (
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <p className="text-xs text-ink-muted">Código de seguimiento</p>
              <p className="font-mono text-lg font-semibold tracking-widest text-ink-primary">
                {solicitud.codigo_seguimiento}
              </p>
            </div>
            <button
              type="button"
              onClick={copiarCodigo}
              className="text-sm font-medium text-ink-link hover:underline"
            >
              {copiado ? '¡Copiado!' : 'Copiar código'}
            </button>
            {solicitud.folio && (
              <div className="sm:ml-6">
                <p className="text-xs text-ink-muted">Folio</p>
                <p className="font-mono text-lg font-semibold text-ink-primary">{solicitud.folio}</p>
              </div>
            )}
          </div>
        ) : confirmando ? (
          <div>
            <p className="text-sm text-ink-primary">
              ¿Confirmas que el pago de <span className="font-semibold">{solicitud.nombre}</span> fue recibido?
              Se generará el código de seguimiento y la solicitud pasará a trámite.
            </p>

            <SelectorEmpresa
              idSolicitud={solicitud.id_solicitud}
              accessToken={accessToken}
              seleccionada={empresa}
              onSeleccionar={setEmpresa}
              onSesionVencida={onSesionVencida}
              deshabilitado={convirtiendo}
            />

            {empresa && (
              <p className="mt-3 text-sm text-ink-primary">
                El trámite quedará vinculado a <span className="font-semibold">{textoEmpresa(empresa)}</span>.
              </p>
            )}

            <CondicionesContrato
              idSolicitud={solicitud.id_solicitud}
              accessToken={accessToken}
              soloSucursal={soloPideSucursal(solicitud.nombre_servicio)}
              onSesionVencida={onSesionVencida}
              onCambio={setContrato}
              deshabilitado={convirtiendo}
            />

            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                onClick={confirmar}
                disabled={convirtiendo || contrato.error !== ''}
                className="bg-brand-primary hover:bg-brand-dark disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-[10px] transition-colors"
              >
                {convirtiendo ? 'Generando código…' : 'Sí, generar código'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmando(false)
                  setEmpresa(null)
                  setContrato(CONTRATO_PENDIENTE)
                  setErrorConversion('')
                }}
                disabled={convirtiendo}
                className="text-sm font-medium text-ink-secondary hover:underline disabled:opacity-60"
              >
                Cancelar
              </button>
            </div>
            {contrato.error && !convirtiendo && (
              <p className="mt-2 text-xs text-ink-muted">{contrato.error}</p>
            )}
          </div>
        ) : (
          <div>
            <button
              type="button"
              onClick={() => setConfirmando(true)}
              disabled={sinServicio}
              className="bg-brand-primary hover:bg-brand-dark disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-[10px] transition-colors"
            >
              Convertir y generar código
            </button>
            {sinServicio && (
              <p className="mt-2 text-xs text-ink-muted">
                Esta solicitud no indica un servicio, por eso no se puede convertir todavía.
              </p>
            )}
          </div>
        )}

        {errorConversion && (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {errorConversion}
          </p>
        )}
      </div>
    </article>
  )
}

export default function Solicitudes() {
  const { accessToken, cerrarSesion } = useAuth()

  const [filtro, setFiltro] = useState('')
  const [pagina, setPagina] = useState(0)
  const [items, setItems] = useState([])
  const [hayMas, setHayMas] = useState(false)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  // Se incrementa para volver a pedir la lista ("Reintentar", "Actualizar", aviso de nuevas).
  const [recarga, setRecarga] = useState(0)

  const haySesion = Boolean(accessToken)

  // Aviso "hay solicitudes nuevas" (consulta cada 30 s, ver useNovedadesSolicitudes.js).
  // `listo` = ya se tomó el punto de partida; recién ahí se carga la lista.
  const { nuevas, listo, reiniciar } = useNovedadesSolicitudes({
    accessToken,
    onSesionVencida: cerrarSesion
  })

  // Un 401 significa sesión vencida o revocada: se cierra la sesión y Panel.jsx redirige al login.
  function manejarError(e) {
    if (e instanceof ApiError && e.status === 401) {
      cerrarSesion()
      return
    }
    setError(e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.')
  }

  useEffect(() => {
    if (!haySesion || !listo) return
    let cancelado = false // evita pisar la lista con una respuesta vieja si cambió el filtro/página
    setCargando(true)
    setError('')

    // Se pide una fila de más para saber si existe una página siguiente sin necesitar un total desde el backend.
    listarSolicitudes({
      accessToken,
      estado: filtro,
      limit: POR_PAGINA + 1,
      offset: pagina * POR_PAGINA
    })
      .then((datos) => {
        if (cancelado) return
        setHayMas(datos.length > POR_PAGINA)
        setItems(datos.slice(0, POR_PAGINA))
      })
      .catch((e) => {
        if (!cancelado) manejarError(e)
      })
      .finally(() => {
        if (!cancelado) setCargando(false)
      })

    return () => {
      cancelado = true
    }
    // accessToken se renueva solo cada ~85 min; no hace falta recargar la lista por eso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haySesion, listo, filtro, pagina, recarga])

  async function convertir(solicitud, { idEmpresa, idSucursal, condiciones }) {
    try {
      const tramite = await convertirSolicitud({
        accessToken,
        idSolicitud: solicitud.id_solicitud,
        idEmpresa,
        idSucursal,
        condiciones
      })
      setItems((prev) =>
        prev.map((s) =>
          s.id_solicitud === solicitud.id_solicitud
            ? {
                ...s,
                estado: 'convertido',
                id_tramite_generado: tramite.id_tramite,
                codigo_seguimiento: tramite.codigo_seguimiento,
                folio: tramite.folio
              }
            : s
        )
      )
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        cerrarSesion()
        return
      }
      throw e // la tarjeta muestra el mensaje junto al botón
    }
  }

  function cambiarFiltro(valor) {
    setFiltro(valor)
    setPagina(0)
  }

  // "Actualizar" y "Reintentar": nuevo punto de partida y se vuelve a pedir la lista (mismo filtro y página).
  async function recargar() {
    await reiniciar()
    setRecarga((n) => n + 1)
  }

  // Clic en el aviso de solicitudes nuevas: vuelve a "Todas" y a la página 1 para que las nuevas (que nacen pendientes) siempre queden 
  // a la vista.
  async function verNuevas() {
    await reiniciar()
    setFiltro('')
    setPagina(0)
    setRecarga((n) => n + 1)
  }

  // La sesión ya la valida Panel.jsx (solo renderiza esta vista si hay usuario).

  const mensajeVacio =
    filtro === 'pendiente'
      ? 'No hay solicitudes pendientes.'
      : filtro === 'convertido'
        ? 'Todavía no hay solicitudes convertidas.'
        : 'Todavía no han llegado solicitudes desde el sitio.'

  // El aviso va en el encabezado (que no se desplaza) para que, al aparecer, la lista que el agente está leyendo no se mueva. 
  // La lista solo cambia si él hace clic.
  const accionesEncabezado = (
    <>
      <span role="status" aria-live="polite" className="contents">
        {nuevas > 0 && (
          <button
            type="button"
            onClick={verNuevas}
            className="text-sm font-semibold text-brand-dark bg-brand-tint border border-brand-primary hover:bg-brand-primary hover:text-white px-4 py-2.5 rounded-[10px] transition-colors"
          >
            {nuevas === 1 ? 'Hay 1 solicitud nueva' : `Hay ${nuevas} solicitudes nuevas`} · Ver
          </button>
        )}
      </span>
      <button
        type="button"
        onClick={recargar}
        disabled={cargando}
        className="text-sm font-medium text-ink-primary bg-surface border border-line-strong hover:border-ink-muted disabled:opacity-60 px-4 py-2.5 rounded-[10px] transition-colors"
      >
        Actualizar
      </button>
    </>
  )

  return (
    <PaginaPanel titulo="Solicitudes de contacto" acciones={accionesEncabezado}>
      <div className="flex gap-2" role="group" aria-label="Filtrar por estado">
        {FILTROS.map((f) => (
          <button
            key={f.valor || 'todas'}
            type="button"
            onClick={() => cambiarFiltro(f.valor)}
            aria-pressed={filtro === f.valor}
            className={`text-sm font-medium px-4 py-2 rounded-full border transition-colors ${
              filtro === f.valor
                ? 'bg-brand-primary border-brand-primary text-white'
                : 'bg-surface border-line text-ink-secondary hover:border-ink-muted'
            }`}
          >
            {f.texto}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-4">
        {error ? (
          <div role="alert" className="bg-surface border border-line rounded-2xl p-6 text-center">
            <p className="text-sm text-red-600">{error}</p>
            <button
              type="button"
              onClick={recargar}
              className="mt-3 text-sm font-medium text-ink-link hover:underline"
            >
              Reintentar
            </button>
          </div>
        ) : cargando && items.length === 0 ? (
          <p className="text-sm text-ink-secondary text-center py-10">Cargando solicitudes…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-ink-secondary text-center py-10">{mensajeVacio}</p>
        ) : (
          <div className={`space-y-4 ${cargando ? 'opacity-60' : ''}`}>
            {items.map((s) => (
              <TarjetaSolicitud
                key={s.id_solicitud}
                solicitud={s}
                accessToken={accessToken}
                onConvertir={convertir}
                onSesionVencida={cerrarSesion}
              />
            ))}
          </div>
        )}
      </div>

      {(pagina > 0 || hayMas) && (
        <div className="mt-6 flex items-center justify-between text-sm font-medium">
          <button
            type="button"
            onClick={() => setPagina((p) => p - 1)}
            disabled={pagina === 0 || cargando}
            className="text-ink-link hover:underline disabled:opacity-40 disabled:no-underline"
          >
            ← Anterior
          </button>
          <span className="text-ink-muted">Página {pagina + 1}</span>
          <button
            type="button"
            onClick={() => setPagina((p) => p + 1)}
            disabled={!hayMas || cargando}
            className="text-ink-link hover:underline disabled:opacity-40 disabled:no-underline"
          >
            Siguiente →
          </button>
        </div>
      )}
    </PaginaPanel>
  )
}