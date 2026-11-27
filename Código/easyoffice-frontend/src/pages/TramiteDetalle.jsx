import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import {
  cancelarTramite, descargarDocumento, generarDocumento, obtenerTramite, reenviarAFirma,
} from '../lib/tramitesApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'
import StatusChip from '../components/StatusChip.jsx'
import { SkeletonTarjeta } from '../components/Skeleton.jsx'

// Detalle de un trámite: firma + seguimiento (mockup Figma, pantalla "4 · Detalle de trámite (firma +
// seguimiento)"). GET /api/tramites/{id}. La "Estado del trámite" del mockup es una maqueta de 5 pasos
// fijos; acá se arma con el historial real (historial_estado), que puede tener más o menos pasos.
// "Reenviar a firma" y "Anular trámite" no existían en el backend: se agregaron junto con esta pantalla
// (POST /api/tramites/{id}/reenviar-firma y /cancelar).

const ESTADOS_SIN_REGENERAR = ['firmado', 'entregado', 'cancelado']
const ESTADOS_NO_CANCELABLES = ['firmado', 'entregado', 'cancelado']

const ORIGEN_TEXTO = { agente: 'Agente', cliente: 'Cliente', sistema: 'Sistema' }

const claseBoton =
  'text-[13px] font-medium px-3 py-1.5 rounded-md border border-line-strong bg-surface text-ink-primary hover:border-ink-muted transition-colors disabled:opacity-50'

const claseBotonPrimario =
  'text-[13px] font-semibold px-3 py-2 rounded-md bg-brand-primary text-white hover:bg-brand-dark transition-colors disabled:opacity-50 w-full text-center'

function formatearFechaHora(iso) {
  if (!iso) return '—'
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`
  const fecha = new Date(conZona)
  if (Number.isNaN(fecha.getTime())) return '—'
  const dia = fecha.toLocaleDateString('es-CL', { day: 'numeric', month: 'short' }).replace('.', '')
  const hora = fecha.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false })
  return `${dia} · ${hora}`
}

function quienOrigino(item) {
  if (item.origen === 'agente') return item.nombre_usuario || 'Agente'
  if (item.origen === 'cliente') return 'El cliente'
  return ORIGEN_TEXTO[item.origen] || item.origen
}

export default function TramiteDetalle() {
  const { idTramite } = useParams()
  const { accessToken, cerrarSesion } = useAuth()

  const [tramite, setTramite] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [noEncontrado, setNoEncontrado] = useState(false)
  const [recarga, setRecarga] = useState(0)

  const [trabajando, setTrabajando] = useState(false)
  const [aviso, setAviso] = useState(null) // { tipo: 'ok' | 'error', texto }
  const [anulando, setAnulando] = useState(false)
  const [motivoAnular, setMotivoAnular] = useState('')

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

    obtenerTramite({ accessToken, idTramite })
      .then((datos) => {
        if (!cancelado) setTramite(datos)
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
  }, [idTramite, recarga])

  async function generarPdf() {
    setTrabajando(true)
    setAviso(null)
    try {
      const doc = await generarDocumento({ accessToken, idTramite: tramite.id_tramite })
      setTramite((t) => ({ ...t, tiene_documento: true, folio: doc.folio ?? t.folio }))
      setAviso({ tipo: 'ok', texto: `Documento generado (plantilla versión ${doc.version_plantilla}).` })
    } catch (e) {
      const mensaje = manejarError(e)
      if (mensaje) setAviso({ tipo: 'error', texto: mensaje })
    } finally {
      setTrabajando(false)
    }
  }

  async function descargarPdf() {
    setTrabajando(true)
    setAviso(null)
    try {
      const blob = await descargarDocumento({ accessToken, idTramite: tramite.id_tramite })
      const url = URL.createObjectURL(blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `${tramite.folio || tramite.codigo_seguimiento}.pdf`
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      const mensaje = manejarError(e)
      if (mensaje) setAviso({ tipo: 'error', texto: mensaje })
    } finally {
      setTrabajando(false)
    }
  }

  async function reenviar() {
    setTrabajando(true)
    setAviso(null)
    try {
      const datos = await reenviarAFirma({ accessToken, idTramite: tramite.id_tramite })
      setTramite(datos)
      setAviso(
        datos.aviso_firma
          ? { tipo: 'error', texto: datos.aviso_firma }
          : { tipo: 'ok', texto: 'Se reintentó el envío a firma.' }
      )
    } catch (e) {
      const mensaje = manejarError(e)
      if (mensaje) setAviso({ tipo: 'error', texto: mensaje })
    } finally {
      setTrabajando(false)
    }
  }

  async function confirmarAnulacion() {
    setTrabajando(true)
    setAviso(null)
    try {
      const datos = await cancelarTramite({ accessToken, idTramite: tramite.id_tramite, comentario: motivoAnular })
      setTramite(datos)
      setAnulando(false)
      setMotivoAnular('')
      setAviso({ tipo: 'ok', texto: 'Trámite anulado.' })
    } catch (e) {
      const mensaje = manejarError(e)
      if (mensaje) setAviso({ tipo: 'error', texto: mensaje })
    } finally {
      setTrabajando(false)
    }
  }

  const volver = (
    <Link to="/panel/tramites" className="text-sm font-medium text-ink-link hover:underline">
      ← Trámites
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
        <p className="text-lg font-semibold text-ink-primary">Este trámite no existe</p>
        <p className="mt-2 text-sm text-ink-secondary">Puede que lo hayan buscado por un enlace viejo.</p>
      </div>
    )
  } else if (cargando && !tramite) {
    contenido = (
      <div className="max-w-5xl grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-5">
        <SkeletonTarjeta lineas={5} />
        <SkeletonTarjeta lineas={5} />
      </div>
    )
  } else if (tramite) {
    const puedeRegenerar = !ESTADOS_SIN_REGENERAR.includes(tramite.estado_actual)
    const puedeCancelar = !ESTADOS_NO_CANCELABLES.includes(tramite.estado_actual)
    const puedeReenviar = Boolean(tramite.aviso_firma) && tramite.estado_actual === 'procesando_firma'

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
          <p className="text-xs text-ink-muted">
            Trámites &nbsp;/&nbsp; {tramite.cliente.nombre}
          </p>
          <div className="flex items-center gap-3 mt-1">
            <h2 className="text-lg font-semibold text-ink-primary">{tramite.nombre_servicio}</h2>
            <StatusChip variant={tramite.estado_actual} />
          </div>
          <p className="text-sm text-ink-muted mt-1">
            {tramite.cliente.rut ? `RUT ${tramite.cliente.rut}` : 'Sin RUT'} ·{' '}
            <span className="font-mono tracking-wider">{tramite.codigo_seguimiento}</span>
            {tramite.folio && ` · Folio ${tramite.folio}`} · {tramite.nombre_agente || 'Sin agente asignado'}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-5 items-start">
          <div className="bg-surface border border-line rounded-[10px] p-6">
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-semibold text-ink-primary">Documento</h3>
              <p className="text-xs text-ink-muted">
                {tramite.tiene_documento ? `PDF generado · actualizado ${formatearFechaHora(tramite.fecha_actualizacion)}` : 'Todavía sin generar'}
              </p>
            </div>
            <div className="mt-4 flex items-center gap-3">
              {!tramite.tiene_documento ? (
                puedeRegenerar ? (
                  <button type="button" onClick={generarPdf} disabled={trabajando} className={claseBoton}>
                    Generar
                  </button>
                ) : (
                  <span className="text-[13px] text-ink-muted">Sin documento</span>
                )
              ) : (
                <>
                  <button type="button" onClick={descargarPdf} disabled={trabajando} className={claseBoton}>
                    Descargar PDF
                  </button>
                  {puedeRegenerar && (
                    <button type="button" onClick={generarPdf} disabled={trabajando} className="text-[13px] font-medium text-ink-link hover:underline disabled:opacity-50">
                      Regenerar
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="space-y-5">
            <div className="bg-surface border border-line rounded-[10px] p-[22px]">
              <h3 className="text-[15px] font-semibold text-ink-primary">Estado del trámite</h3>
              <p className="text-xs text-ink-secondary mt-0.5 mb-4">Se actualiza solo con los eventos registrados en el sistema.</p>
              <div className="space-y-4">
                {tramite.historial.map((item, i) => (
                  <div key={i} className="relative pl-0">
                    <div className="flex items-start gap-2">
                      <StatusChip variant={item.estado} />
                    </div>
                    <p className="text-xs text-ink-secondary mt-1">
                      {quienOrigino(item)} · {formatearFechaHora(item.fecha)}
                    </p>
                    {item.comentario && <p className="text-xs text-ink-muted mt-0.5">{item.comentario}</p>}
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-surface border border-line rounded-[10px] p-[22px] space-y-3">
              <h3 className="text-[15px] font-semibold text-ink-primary">Acciones</h3>
              {puedeReenviar && (
                <button type="button" onClick={reenviar} disabled={trabajando} className={claseBotonPrimario}>
                  Reenviar a firma
                </button>
              )}
              {puedeCancelar && !anulando && (
                <button
                  type="button"
                  onClick={() => setAnulando(true)}
                  disabled={trabajando}
                  className="text-[13px] font-medium text-status-rejected-fg hover:underline disabled:opacity-50"
                >
                  Anular trámite
                </button>
              )}
              {anulando && (
                <div className="space-y-2">
                  <textarea
                    value={motivoAnular}
                    onChange={(e) => setMotivoAnular(e.target.value)}
                    placeholder="Motivo de la anulación (opcional)"
                    maxLength={500}
                    rows={2}
                    className="w-full text-[13px] rounded-md border border-line-strong p-2 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                  />
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={confirmarAnulacion}
                      disabled={trabajando}
                      className="text-[13px] font-semibold px-3 py-1.5 rounded-md bg-status-rejected-fg text-white disabled:opacity-50"
                    >
                      Confirmar anulación
                    </button>
                    <button
                      type="button"
                      onClick={() => { setAnulando(false); setMotivoAnular('') }}
                      disabled={trabajando}
                      className="text-[13px] font-medium text-ink-secondary hover:underline disabled:opacity-50"
                    >
                      No anular
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <PaginaPanel titulo="Detalle del trámite" acciones={volver}>
      {contenido}
    </PaginaPanel>
  )
}
