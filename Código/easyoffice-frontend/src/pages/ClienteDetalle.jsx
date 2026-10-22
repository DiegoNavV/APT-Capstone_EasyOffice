import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import { obtenerCliente } from '../lib/clientesApi.js'
import { descargarDocumento, generarDocumento } from '../lib/tramitesApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'
import StatusChip from '../components/StatusChip.jsx'

// Ficha de cliente 360° (mockup Figma, pantalla "6 · Ficha de cliente 360°"): datos de contacto, empresas vinculadas
// y el historial completo de trámites, con los mismos botones Generar/Descargar que la vista de Trámites.
// GET /api/clientes/{id}.

const ESTADOS_SIN_REGENERAR = ['firmado', 'entregado']

const claseBoton =
  'text-[13px] font-medium px-3 py-1.5 rounded-md border border-line-strong bg-surface text-ink-primary hover:border-ink-muted transition-colors disabled:opacity-50'

function formatearFecha(iso) {
  if (!iso) return '—'
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`
  const fecha = new Date(conZona)
  if (Number.isNaN(fecha.getTime())) return '—'
  return fecha.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' }).replace('.', '')
}

// Las claves de `empresa.datos` varían según el servicio (ver app/campos_servicio.py); se muestran tal como vienen,
// convirtiendo "razon_social_real" -> "Razon social real" para que no se vea como una variable de código.
function etiquetaCampo(clave) {
  const texto = clave.replaceAll('_', ' ')
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

export default function ClienteDetalle() {
  const { idCliente } = useParams()
  const { accessToken, cerrarSesion } = useAuth()

  const [cliente, setCliente] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [noEncontrado, setNoEncontrado] = useState(false)
  const [recarga, setRecarga] = useState(0)

  const [trabajando, setTrabajando] = useState(null) // id_tramite en curso, o null
  const [aviso, setAviso] = useState(null) // { tipo: 'ok' | 'error', texto }

  function manejarError(e) {
    if (e instanceof ApiError && e.status === 401) {
      cerrarSesion()
      return null
    }
    return e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.'
  }

  useEffect(() => {
    let cancelado = false
    setCargando(true)
    setError('')
    setNoEncontrado(false)

    obtenerCliente({ accessToken, idCliente })
      .then((datos) => {
        if (!cancelado) setCliente(datos)
      })
      .catch((e) => {
        if (cancelado) return
        if (e instanceof ApiError && e.status === 404) {
          setNoEncontrado(true)
          return
        }
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
  }, [idCliente, recarga])

  async function generarPdf(t) {
    setTrabajando(t.id_tramite)
    setAviso(null)
    try {
      const doc = await generarDocumento({ accessToken, idTramite: t.id_tramite })
      setCliente((c) => ({
        ...c,
        tramites: c.tramites.map((f) => (f.id_tramite === t.id_tramite ? { ...f, tiene_documento: true, folio: doc.folio ?? f.folio } : f)),
      }))
      setAviso({ tipo: 'ok', texto: `Documento generado (plantilla versión ${doc.version_plantilla}).` })
    } catch (e) {
      const mensaje = manejarError(e)
      if (mensaje) setAviso({ tipo: 'error', texto: mensaje })
    } finally {
      setTrabajando(null)
    }
  }

  async function descargarPdf(t) {
    setTrabajando(t.id_tramite)
    setAviso(null)
    try {
      const blob = await descargarDocumento({ accessToken, idTramite: t.id_tramite })
      const url = URL.createObjectURL(blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `${t.folio || t.codigo_seguimiento}.pdf`
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      const mensaje = manejarError(e)
      if (mensaje) setAviso({ tipo: 'error', texto: mensaje })
    } finally {
      setTrabajando(null)
    }
  }

  function accionesDocumento(t) {
    const ocupado = trabajando !== null
    const puedeRegenerar = !ESTADOS_SIN_REGENERAR.includes(t.estado_actual)
    if (trabajando === t.id_tramite) return <span className="text-[13px] text-ink-muted">Un momento…</span>
    if (!t.tiene_documento) {
      return puedeRegenerar ? (
        <button type="button" onClick={() => generarPdf(t)} disabled={ocupado} className={claseBoton}>
          Generar
        </button>
      ) : (
        <span className="text-[13px] text-ink-muted">Sin documento</span>
      )
    }
    return (
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => descargarPdf(t)} disabled={ocupado} className={claseBoton}>
          Descargar
        </button>
        {puedeRegenerar && (
          <button
            type="button"
            onClick={() => generarPdf(t)}
            disabled={ocupado}
            className="text-[13px] font-medium text-ink-link hover:underline disabled:opacity-50"
          >
            Regenerar
          </button>
        )}
      </div>
    )
  }

  const volver = (
    <Link to="/panel/clientes" className="text-sm font-medium text-ink-link hover:underline">
      ← Clientes
    </Link>
  )

  let contenido
  if (error) {
    contenido = (
      <div role="alert" className="text-center py-10">
        <p className="text-sm text-red-600">{error}</p>
        <button type="button" onClick={() => setRecarga((n) => n + 1)} className="mt-3 text-sm font-medium text-ink-link hover:underline">
          Reintentar
        </button>
      </div>
    )
  } else if (noEncontrado) {
    contenido = (
      <div className="max-w-xl mx-auto text-center py-16">
        <p className="text-lg font-semibold text-ink-primary">Este cliente no existe</p>
        <p className="mt-2 text-sm text-ink-secondary">Puede que lo hayan buscado por un enlace viejo.</p>
      </div>
    )
  } else if (cargando && !cliente) {
    contenido = <p className="text-sm text-ink-secondary text-center py-10">Cargando ficha…</p>
  } else if (cliente) {
    contenido = (
      <div className="max-w-5xl space-y-5">
        {aviso && (
          <p
            role={aviso.tipo === 'error' ? 'alert' : 'status'}
            className={`text-sm rounded-lg px-4 py-2.5 ${
              aviso.tipo === 'error' ? 'text-red-600 bg-red-50 border border-red-200' : 'text-status-signed-fg bg-status-signed-bg'
            }`}
          >
            {aviso.texto}
          </p>
        )}

        <div className="bg-surface border border-line rounded-[10px] px-6 py-5">
          <h2 className="text-lg font-semibold text-ink-primary">{cliente.nombre}</h2>
          <p className="text-sm text-ink-muted mt-0.5">{cliente.rut ? `RUT ${cliente.rut}` : 'Sin RUT'} · Cliente desde {formatearFecha(cliente.fecha_creacion)}</p>
          <div className="flex gap-10 mt-4 text-sm">
            <div>
              <p className="text-ink-muted text-xs font-medium">Email</p>
              <p className="text-ink-primary">{cliente.email || '—'}</p>
            </div>
            <div>
              <p className="text-ink-muted text-xs font-medium">Teléfono</p>
              <p className="text-ink-primary">{cliente.telefono || '—'}</p>
            </div>
            <div>
              <p className="text-ink-muted text-xs font-medium">Trámites</p>
              <p className="text-ink-primary">{cliente.tramites.length}</p>
            </div>
          </div>
        </div>

        {cliente.empresas.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-ink-primary mb-3">Empresas vinculadas</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {cliente.empresas.map((e) => (
                <div key={e.id_empresa} className="bg-surface border border-line rounded-[10px] px-5 py-4">
                  <p className="text-sm font-semibold text-ink-primary">{e.razon_social}</p>
                  <p className="text-xs text-ink-muted mb-2">RUT {e.rut_empresa}</p>
                  {Object.entries(e.datos).length > 0 && (
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 pt-2 border-t border-line">
                      {Object.entries(e.datos).map(([clave, valor]) => (
                        <div key={clave} className="min-w-0">
                          <dt className="text-[11px] text-ink-muted">{etiquetaCampo(clave)}</dt>
                          <dd className="text-[13px] text-ink-secondary truncate" title={String(valor)}>{String(valor)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <h3 className="text-sm font-semibold text-ink-primary mb-3">Trámites</h3>
          <div className="bg-surface border border-line rounded-[10px] overflow-hidden">
            <div className="bg-subtle border-b border-line flex items-center px-4 py-[11px] text-[11px] font-semibold tracking-wide text-ink-muted">
              <span className="flex-1">DOCUMENTO</span>
              <span className="w-[170px]">AGENTE</span>
              <span className="w-[140px]">CREADO</span>
              <span className="w-[140px]">ESTADO</span>
              <span className="w-[180px] text-right">PDF</span>
            </div>
            {cliente.tramites.length === 0 ? (
              <p className="text-sm text-ink-secondary text-center py-10">Este cliente todavía no tiene trámites.</p>
            ) : (
              cliente.tramites.map((t) => (
                <div key={t.id_tramite} className="border-b border-line last:border-b-0 flex items-center px-4 py-[13px]">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-ink-primary">{t.nombre_servicio}</p>
                    <p className="text-xs text-ink-muted">
                      <span className="font-mono tracking-wider">{t.codigo_seguimiento}</span>
                      {t.folio && ` · Folio ${t.folio}`}
                    </p>
                  </div>
                  <span className="w-[170px] text-[13px] text-ink-secondary">{t.nombre_agente || 'Sin asignar'}</span>
                  <span className="w-[140px] text-[13px] text-ink-secondary">{formatearFecha(t.fecha_creacion)}</span>
                  <span className="w-[140px]">
                    <StatusChip variant={t.estado_actual} />
                  </span>
                  <span className="w-[180px] flex justify-end">{accionesDocumento(t)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <PaginaPanel titulo={cliente ? cliente.nombre : 'Cliente'} acciones={volver}>
      {contenido}
    </PaginaPanel>
  )
}
