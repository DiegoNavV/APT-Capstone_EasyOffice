import { useEffect, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import { obtenerReporteTramites } from '../lib/tramitesApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'
import StatusChip from '../components/StatusChip.jsx'

// Vista "Reportes" del panel (mockup Figma, pantalla "9 · Exportar reporte"), con los conteos agregados reales de
// GET /api/tramites/reporte. Exclusiva de administradores -- confirmado con el cliente (ver
// Resumen_Alcance_Proyecto_EasyOffice.docx: "panel de resumen" es una función exclusiva del administrador), por eso
// el backend decide con `puede_ver` en vez de ocultar el link en el Sidebar.
// Exportar a PDF/Excel/Word (como en el mockup) todavía no está construido: esta vista solo muestra los conteos.

function Barra({ porcentaje }) {
  return (
    <div className="flex-1 min-w-0 h-1.5 rounded-full bg-subtle overflow-hidden">
      <div className="h-full rounded-full bg-brand-primary" style={{ width: `${porcentaje}%` }} />
    </div>
  )
}

function FilaConteo({ etiqueta, cantidad, total, children }) {
  const porcentaje = total > 0 ? Math.round((cantidad / total) * 100) : 0
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="w-[152px] shrink-0 truncate text-sm text-ink-primary" title={etiqueta}>
        {children ?? etiqueta}
      </div>
      <Barra porcentaje={porcentaje} />
      <span className="w-9 shrink-0 text-right text-sm font-semibold text-ink-primary">{cantidad}</span>
    </div>
  )
}

function SeccionConteo({ titulo, filas, total, etiquetaVacio, renderEtiqueta }) {
  return (
    <div className="bg-surface border border-line rounded-[10px] px-5 py-[18px]">
      <p className="text-sm font-semibold text-ink-primary mb-3">{titulo}</p>
      {filas.length === 0 ? (
        <p className="text-sm text-ink-muted py-2">{etiquetaVacio}</p>
      ) : (
        filas.map((f) => (
          <FilaConteo key={f.etiqueta} etiqueta={f.etiqueta} cantidad={f.cantidad} total={total}>
            {renderEtiqueta ? renderEtiqueta(f.etiqueta) : undefined}
          </FilaConteo>
        ))
      )}
    </div>
  )
}

export default function Reportes() {
  const { accessToken, cerrarSesion } = useAuth()
  const haySesion = Boolean(accessToken)

  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [recarga, setRecarga] = useState(0)

  // Un 401 significa sesión vencida o revocada: se cierra la sesión y Panel.jsx redirige al login.
  function mensajeDe(e) {
    if (e instanceof ApiError && e.status === 401) {
      cerrarSesion()
      return null
    }
    return e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.'
  }

  useEffect(() => {
    if (!haySesion) return
    let cancelado = false
    setCargando(true)
    setError('')
    obtenerReporteTramites({ accessToken })
      .then((d) => {
        if (!cancelado) setDatos(d)
      })
      .catch((e) => {
        if (cancelado) return
        const m = mensajeDe(e)
        if (m) setError(m)
      })
      .finally(() => {
        if (!cancelado) setCargando(false)
      })
    return () => {
      cancelado = true
    }
    // accessToken se renueva solo cada ~85 min; no hace falta recargar por eso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haySesion, recarga])

  const acciones = (
    <button
      type="button"
      onClick={() => setRecarga((n) => n + 1)}
      disabled={cargando}
      className="text-sm font-medium text-ink-primary bg-surface border border-line-strong hover:border-ink-muted disabled:opacity-60 px-4 py-2.5 rounded-[10px] transition-colors"
    >
      Actualizar
    </button>
  )

  let contenido
  if (error && !datos) {
    contenido = (
      <div role="alert" className="text-center py-10">
        <p className="text-sm text-red-600">{error}</p>
        <button type="button" onClick={() => setRecarga((n) => n + 1)} className="mt-3 text-sm font-medium text-ink-link hover:underline">
          Reintentar
        </button>
      </div>
    )
  } else if (cargando && !datos) {
    contenido = <p className="text-sm text-ink-secondary text-center py-10">Cargando reportes…</p>
  } else if (datos && !datos.puede_ver) {
    contenido = (
      <div className="max-w-xl mx-auto text-center py-16">
        <p className="text-lg font-semibold text-ink-primary">No tienes permiso para ver reportes</p>
        <p className="mt-2 text-sm text-ink-secondary">Los reportes son exclusivos de administradores. Si lo necesitas, pídele acceso a uno.</p>
      </div>
    )
  } else if (datos && datos.total === 0) {
    contenido = (
      <div className="max-w-xl mx-auto text-center py-16">
        <p className="text-lg font-semibold text-ink-primary">Todavía no hay suficiente información</p>
        <p className="mt-2 text-sm text-ink-secondary">
          Los reportes se generan a partir de los trámites existentes. En cuanto se convierta la primera solicitud en un trámite, van a aparecer acá.
        </p>
      </div>
    )
  } else if (datos) {
    contenido = (
      <div className="max-w-6xl space-y-5">
        {error && (
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
            {error}
          </p>
        )}

        <div className="bg-surface border border-line rounded-[10px] px-5 py-[18px] inline-block">
          <p className="text-[13px] font-medium text-ink-secondary">Total de trámites</p>
          <p className="text-[26px] font-bold text-ink-primary leading-[32px]">{datos.total}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SeccionConteo
            titulo="Por estado"
            filas={datos.por_estado}
            total={datos.total}
            etiquetaVacio="Sin datos."
            renderEtiqueta={(estado) => <StatusChip variant={estado} />}
          />
          <SeccionConteo titulo="Por servicio" filas={datos.por_servicio} total={datos.total} etiquetaVacio="Sin datos." />
          <SeccionConteo
            titulo="Por agente"
            filas={datos.por_agente}
            total={datos.total}
            etiquetaVacio="Ningún trámite tiene un agente responsable asignado."
          />
        </div>
      </div>
    )
  }

  return <PaginaPanel titulo="Reportes" acciones={acciones}>{contenido}</PaginaPanel>
}
