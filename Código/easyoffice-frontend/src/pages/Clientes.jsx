import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import { listarClientes } from '../lib/clientesApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'

// Vista "Clientes" del panel (mockup Figma, pantalla "5 · Listado de clientes"), conectada a GET /api/clientes
// (lista, búsqueda y paginación en el servidor). Cada cliente sale con cuántos trámites tiene.
// Cada fila lleva a su ficha 360° (pantalla 6 del mockup, ver ClienteDetalle.jsx).

const POR_PAGINA = 15
const PAUSA_BUSQUEDA_MS = 300

// "22 oct 2026" -- a diferencia de "actualizado" en Trámites, acá importa la antigüedad, no la recencia.
function formatearFecha(iso) {
  if (!iso) return '—'
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`
  const fecha = new Date(conZona)
  if (Number.isNaN(fecha.getTime())) return '—'
  return fecha.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' }).replace('.', '')
}

export default function Clientes() {
  const { accessToken, cerrarSesion } = useAuth()
  const haySesion = Boolean(accessToken)

  const [busqueda, setBusqueda] = useState('') // lo que se escribe
  const [q, setQ] = useState('') // lo que se envía al servidor (con pausa)
  const [pagina, setPagina] = useState(0)

  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [recarga, setRecarga] = useState(0)

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

  useEffect(() => {
    if (!haySesion) return
    let cancelado = false
    setCargando(true)
    setError('')

    listarClientes({ accessToken, q, limit: POR_PAGINA, offset: pagina * POR_PAGINA })
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
  }, [haySesion, q, pagina, recarga])

  const totalPaginas = Math.max(1, Math.ceil(total / POR_PAGINA))

  const acciones = (
    <>
      <input
        type="search"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        placeholder="Buscar nombre o RUT…"
        aria-label="Buscar clientes"
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
    </>
  )

  return (
    <PaginaPanel titulo="Clientes" acciones={acciones}>
      <div className="bg-surface border border-line rounded-[10px] overflow-hidden">
        <div className="bg-subtle border-b border-line flex items-center px-4 py-[11px] text-[11px] font-semibold tracking-wide text-ink-muted">
          <span className="flex-1">NOMBRE / RUT</span>
          <span className="w-[230px]">CONTACTO</span>
          <span className="w-[120px] text-right">TRÁMITES</span>
          <span className="w-[150px] text-right">CLIENTE DESDE</span>
        </div>

        {error ? (
          <div role="alert" className="text-center py-10">
            <p className="text-sm text-red-600">{error}</p>
            <button type="button" onClick={() => setRecarga((n) => n + 1)} className="mt-3 text-sm font-medium text-ink-link hover:underline">
              Reintentar
            </button>
          </div>
        ) : cargando && items.length === 0 ? (
          <p className="text-sm text-ink-secondary text-center py-10">Cargando clientes…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-ink-secondary text-center py-10">
            {q ? 'Ningún cliente coincide con la búsqueda.' : 'Todavía no hay clientes. Se crean al convertir una solicitud en trámite.'}
          </p>
        ) : (
          <div className={cargando ? 'opacity-60' : ''}>
            {items.map((c) => (
              <Link
                key={c.id_cliente}
                to={`/panel/clientes/${c.id_cliente}`}
                className="border-b border-line last:border-b-0 cursor-pointer flex items-center px-4 py-[13px] hover:bg-canvas transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-ink-primary">{c.nombre}</p>
                  <p className="text-xs text-ink-muted">{c.rut ? `RUT ${c.rut}` : 'Sin RUT'}</p>
                </div>
                <div className="w-[230px] min-w-0">
                  <p className="text-[13px] text-ink-secondary truncate">{c.email || '—'}</p>
                  <p className="text-xs text-ink-muted">{c.telefono || '—'}</p>
                </div>
                <span className="w-[120px] text-right text-[13px] font-semibold text-ink-primary">{c.cantidad_tramites}</span>
                <span className="w-[150px] text-right text-[13px] text-ink-secondary">{formatearFecha(c.fecha_creacion)}</span>
              </Link>
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
            Página {pagina + 1} de {totalPaginas} · {total} clientes
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
