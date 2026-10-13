import { useEffect, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import { listarTramites, obtenerResumenTramites } from '../lib/tramitesApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'
import StatusChip from '../components/StatusChip.jsx'

// Vista "panel principal" (mockup Figma, pantalla "2 · Listado de trámites"), conectada al backend: GET /api/tramites 
// (lista, filtros, búsqueda y paginación en el servidor) y GET /api/tramites/resumen (KPIs y opciones de los filtros). 
// "+ Nuevo trámite" y el clic en una fila todavía no hacen nada porque esas funcionalidades no están construidas.

const POR_PAGINA = 10
const PAUSA_BUSQUEDA_MS = 300

// Orden del ciclo de vida de un trámite; coincide con `estado_actual` del backend.
const ESTADOS = [
  { valor: 'generado', texto: 'Generado' },
  { valor: 'procesando_firma', texto: 'Procesando firma' },
  { valor: 'en_revision', texto: 'En revisión' },
  { valor: 'firmado', texto: 'Firmado' },
  { valor: 'entregado', texto: 'Entregado' }
]

const KPIS = [
  { clave: 'pendientes_datos', etiqueta: 'Pendientes de datos', nota: 'El cliente aún no completa sus datos' },
  { clave: 'en_proceso', etiqueta: 'En proceso', nota: 'Firma o revisión en curso' },
  { clave: 'firmados_24h', etiqueta: 'Firmados (24 h)', nota: 'En las últimas 24 horas' },
  { clave: 'entregados', etiqueta: 'Entregados', nota: 'Documento entregado' }
]

const claseFiltro = (activo) =>
  `text-[13px] font-medium px-3 py-[7px] rounded-md border transition-colors ${
    activo ? 'bg-brand-tint border-brand-primary text-brand-dark' : 'bg-surface border-line-strong text-ink-secondary hover:border-ink-muted'
  }`

const claseSelect =
  'text-[13px] font-medium px-3 py-[7px] rounded-md border border-line-strong bg-surface text-ink-secondary focus:outline-none focus:ring-2 focus:ring-brand-primary'

// "Hoy · 10:24", "Ayer · 17:45", "12 sep · 11:30" (formato del mockup).
function formatearActualizado(iso, ahora = new Date()) {
  if (!iso) return '—'
  // El backend guarda la fecha en UTC pero la devuelve sin zona horaria
  // ("2026-10-08T19:42:11"); sin la "Z" el navegador la tomaría como hora local.
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`
  const fecha = new Date(conZona)
  if (Number.isNaN(fecha.getTime())) return '—'

  const hora = fecha.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false })
  const diaDe = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const dias = Math.round((diaDe(ahora) - diaDe(fecha)) / 86_400_000)
  if (dias === 0) return `Hoy · ${hora}`
  if (dias === 1) return `Ayer · ${hora}`
  const dia = fecha.toLocaleDateString('es-CL', { day: 'numeric', month: 'short' }).replace('.', '')
  return `${dia} · ${hora}`
}

export default function Tramites() {
  const { accessToken, cerrarSesion } = useAuth()
  const haySesion = Boolean(accessToken)

  const [busqueda, setBusqueda] = useState('') // lo que se escribe
  const [q, setQ] = useState('') // lo que se envía al servidor (con pausa)
  const [servicioId, setServicioId] = useState('')
  const [estado, setEstado] = useState('')
  const [agenteId, setAgenteId] = useState('')
  const [pagina, setPagina] = useState(0)

  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [resumen, setResumen] = useState(null) // { kpis, servicios, agentes }
  // Se incrementa para volver a pedir todo ("Actualizar", "Reintentar").
  const [recarga, setRecarga] = useState(0)

  // Un 401 significa sesión vencida o revocada: se cierra la sesión y Panel.jsx redirige al login.
  function manejarError(e) {
    if (e instanceof ApiError && e.status === 401) {
      cerrarSesion()
      return null
    }
    return e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.'
  }

  // Búsqueda con pausa: no se consulta en cada tecla.
  useEffect(() => {
    const texto = busqueda.trim()
    if (texto === q) return
    const id = setTimeout(() => {
      setQ(texto)
      setPagina(0)
    }, PAUSA_BUSQUEDA_MS)
    return () => clearTimeout(id)
  }, [busqueda, q])

  // KPIs y opciones de los filtros. Si falla, la lista sigue funcionando (los KPIs muestran "—").
  useEffect(() => {
    if (!haySesion) return
    let cancelado = false
    obtenerResumenTramites({ accessToken })
      .then((datos) => {
        if (!cancelado) setResumen(datos)
      })
      .catch((e) => {
        if (!cancelado) manejarError(e)
      })
    return () => {
      cancelado = true
    }
    // accessToken se renueva solo cada ~85 min; no hace falta recargar por eso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haySesion, recarga])

  // Lista de trámites con los filtros actuales.
  useEffect(() => {
    if (!haySesion) return
    let cancelado = false // evita pisar la lista con una respuesta vieja si cambió un filtro
    setCargando(true)
    setError('')

    listarTramites({
      accessToken,
      servicioId,
      estado,
      agenteId,
      q,
      limit: POR_PAGINA,
      offset: pagina * POR_PAGINA
    })
      .then((datos) => {
        if (cancelado) return
        setItems(datos.items)
        setTotal(datos.total)
      })
      .catch((e) => {
        if (cancelado) return
        const mensaje = manejarError(e)
        if (mensaje) setError(mensaje)
      })
      .finally(() => {
        if (!cancelado) setCargando(false)
      })

    return () => {
      cancelado = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haySesion, servicioId, estado, agenteId, q, pagina, recarga])

  function cambiarFiltro(setter) {
    return (valor) => {
      setter(valor)
      setPagina(0)
    }
  }

  const hayFiltros = Boolean(servicioId || estado || agenteId || q)
  const totalPaginas = Math.max(1, Math.ceil(total / POR_PAGINA))
  const servicios = resumen?.servicios ?? []
  const agentes = resumen?.agentes ?? []

  // Filas que todavía no hacen nada al hacer clic (no existe vista de detalle construida).
  function detenerClic(e) {
    e.preventDefault()
  }

  const acciones = (
    <>
      <input
        type="search"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        placeholder="Buscar cliente, RUT o código…"
        aria-label="Buscar trámites"
        className="bg-subtle text-sm text-ink-primary placeholder:text-ink-muted rounded-md pl-3 pr-4 py-2.5 w-64 focus:outline-none focus:ring-2 focus:ring-brand-primary"
      />
      <button
        type="button"
        onClick={() => setRecarga((n) => n + 1)}
        disabled={cargando}
        className="text-sm font-medium text-ink-primary bg-surface border border-line-strong hover:border-ink-muted disabled:opacity-60 px-4 py-2.5 rounded-[10px] transition-colors"
      >
        Actualizar
      </button>
      {/* Todavía no está construido el flujo de creación de trámites. */}
      <button
        type="button"
        onClick={detenerClic}
        className="bg-brand-primary hover:bg-brand-dark text-white text-sm font-semibold px-6 py-3 rounded-[10px] transition-colors"
      >
        + Nuevo trámite
      </button>
    </>
  )

  return (
    <PaginaPanel titulo="Trámites" acciones={acciones}>
      <div className="flex gap-4">
        {KPIS.map((kpi) => (
          <div key={kpi.clave} className="bg-surface border border-line rounded-[10px] flex-1 px-5 py-[18px]">
            <p className="text-[13px] font-medium text-ink-secondary">{kpi.etiqueta}</p>
            <p className="text-[26px] font-bold text-ink-primary leading-[32px]">{resumen ? resumen.kpis[kpi.clave] : '—'}</p>
            <p className="text-xs text-ink-muted">{kpi.nota}</p>
          </div>
        ))}
      </div>

      <div className="bg-surface border border-line rounded-[10px] mt-5 overflow-hidden">
        <div className="border-b border-line flex items-center gap-2.5 px-4 py-3.5">
          <div className="flex gap-1.5" role="group" aria-label="Filtrar por documento">
            <button type="button" onClick={() => cambiarFiltro(setServicioId)('')} aria-pressed={servicioId === ''} className={claseFiltro(servicioId === '')}>
              Todos
            </button>
            {servicios.map((s) => (
              <button
                key={s.id_servicio}
                type="button"
                onClick={() => cambiarFiltro(setServicioId)(s.id_servicio)}
                aria-pressed={servicioId === s.id_servicio}
                className={claseFiltro(servicioId === s.id_servicio)}
              >
                {s.nombre}
              </button>
            ))}
          </div>
          <div className="flex-1" />
          <select value={estado} onChange={(e) => cambiarFiltro(setEstado)(e.target.value)} aria-label="Filtrar por estado" className={claseSelect}>
            <option value="">Estado: todos</option>
            {ESTADOS.map((e) => (
              <option key={e.valor} value={e.valor}>
                {e.texto}
              </option>
            ))}
          </select>
          <select
            value={agenteId}
            onChange={(e) => cambiarFiltro(setAgenteId)(e.target.value ? Number(e.target.value) : '')}
            aria-label="Filtrar por agente"
            className={claseSelect}
          >
            <option value="">Agente: todos</option>
            {agentes.map((a) => (
              <option key={a.id_usuario} value={a.id_usuario}>
                {a.nombre}
              </option>
            ))}
          </select>
        </div>

        <div className="bg-subtle border-b border-line flex items-center px-4 py-[11px] text-[11px] font-semibold tracking-wide text-ink-muted">
          <span className="flex-1">SOLICITANTE / EMPRESA</span>
          <span className="w-[230px]">DOCUMENTO</span>
          <span className="w-[170px]">AGENTE</span>
          <span className="w-[150px]">ACTUALIZADO</span>
          <span className="w-[150px]">ESTADO</span>
        </div>

        {error ? (
          <div role="alert" className="text-center py-10">
            <p className="text-sm text-red-600">{error}</p>
            <button type="button" onClick={() => setRecarga((n) => n + 1)} className="mt-3 text-sm font-medium text-ink-link hover:underline">
              Reintentar
            </button>
          </div>
        ) : cargando && items.length === 0 ? (
          <p className="text-sm text-ink-secondary text-center py-10">Cargando trámites…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-ink-secondary text-center py-10">
            {hayFiltros ? 'Ningún trámite coincide con los filtros.' : 'Todavía no hay trámites. Se crean al convertir una solicitud.'}
          </p>
        ) : (
          <div className={cargando ? 'opacity-60' : ''}>
            {items.map((t) => (
              // No hay vista de detalle construida todavía: la fila no navega a ningún lado.
              <a key={t.id_tramite} href="#" onClick={detenerClic} className="border-b border-line last:border-b-0 cursor-pointer flex items-center px-4 py-[13px] hover:bg-canvas transition-colors">
                <div className="flex-1 min-w-0">
                  <p
                    className="text-sm font-medium text-ink-primary"
                    title={t.cliente.datos_pendientes ? 'Nombre de quien hizo la solicitud. Se confirma con el cliente cuando complete los datos de su empresa.' : undefined}
                  >
                    {t.cliente.nombre}
                  </p>
                  <p className="text-xs text-ink-muted">
                    {t.cliente.datos_pendientes && 'Solicitante · '}
                    {t.cliente.rut ? `RUT ${t.cliente.rut}` : 'Sin RUT'} · <span className="font-mono tracking-wider">{t.codigo_seguimiento}</span>
                    {t.cliente.datos_pendientes && ' · Datos de empresa pendientes'}
                  </p>
                </div>
                <span className="w-[230px] text-[13px] text-ink-secondary">{t.nombre_servicio}</span>
                <span className="w-[170px] text-[13px] text-ink-secondary">{t.nombre_agente || 'Sin asignar'}</span>
                <span className="w-[150px] text-[13px] text-ink-secondary">{formatearActualizado(t.fecha_actualizacion)}</span>
                <span className="w-[150px]">
                  <StatusChip variant={t.estado_actual} />
                </span>
              </a>
            ))}
          </div>
        )}
      </div>

      {total > POR_PAGINA && (
        <div className="mt-6 flex items-center justify-between text-sm font-medium">
          <button
            type="button"
            onClick={() => setPagina((p) => p - 1)}
            disabled={pagina === 0 || cargando}
            className="text-ink-link hover:underline disabled:opacity-40 disabled:no-underline"
          >
            ← Anterior
          </button>
          <span className="text-ink-muted">
            Página {pagina + 1} de {totalPaginas} · {total} trámites
          </span>
          <button
            type="button"
            onClick={() => setPagina((p) => p + 1)}
            disabled={pagina + 1 >= totalPaginas || cargando}
            className="text-ink-link hover:underline disabled:opacity-40 disabled:no-underline"
          >
            Siguiente →
          </button>
        </div>
      )}
    </PaginaPanel>
  )
}