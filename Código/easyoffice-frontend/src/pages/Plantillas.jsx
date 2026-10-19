import { useEffect, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import {
  activarPlantilla,
  descargarPlantilla,
  listarPlantillas,
  obtenerConfiguracionPlantillas,
  subirPlantilla
} from '../lib/plantillasApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'

// Gestión de plantillas de documentos (contrato, autorización...). Cada archivo que se sube es una versión nueva del servicio: 
// las anteriores se conservan y solo una está activa. El permiso lo decide el backend (`puede_gestionar`); quien no lo tiene ve solo un aviso.

// "12 oct 2026 · 10:24". El backend devuelve la fecha en UTC sin zona horaria.
function formatearFecha(iso) {
  if (!iso) return '—'
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`
  const fecha = new Date(conZona)
  if (Number.isNaN(fecha.getTime())) return '—'
  const dia = fecha.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' }).replace(/\./g, '')
  const hora = fecha.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false })
  return `${dia} · ${hora}`
}

function formatearTamano(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const claseBotonPrimario =
  'bg-brand-primary hover:bg-brand-dark disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold px-4 py-2 rounded-[10px] transition-colors'
const claseBotonSecundario =
  'text-sm font-semibold text-brand-dark bg-brand-tint border border-brand-primary hover:bg-brand-primary hover:text-white disabled:opacity-60 disabled:cursor-not-allowed px-3 py-1.5 rounded-[10px] transition-colors'

function FormularioSubida({ servicio, maxMb, accessToken, onSubida, onError }) {
  const [archivo, setArchivo] = useState(null)
  const [activar, setActivar] = useState(true)
  const [subiendo, setSubiendo] = useState(false)
  const [claveArchivo, setClaveArchivo] = useState(0) // cambia para vaciar el selector de archivo

  async function enviar(e) {
    e.preventDefault()
    if (!archivo || subiendo) return
    setSubiendo(true)
    try {
      const nueva = await subirPlantilla({ accessToken, idServicio: servicio.id_servicio, archivo, activar })
      setArchivo(null)
      setClaveArchivo((n) => n + 1)
      await onSubida(nueva)
    } catch (err) {
      onError(err)
    } finally {
      setSubiendo(false)
    }
  }

  return (
    <form onSubmit={enviar} className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-line pt-4">
      <input
        key={claveArchivo}
        type="file"
        accept=".docx"
        aria-label={`Archivo Word para ${servicio.nombre}`}
        onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
        disabled={subiendo}
        className="text-sm text-ink-secondary file:mr-3 file:rounded-md file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink-secondary"
      />
      <label className="flex items-center gap-2 text-sm text-ink-primary">
        <input type="checkbox" checked={activar} onChange={(e) => setActivar(e.target.checked)} disabled={subiendo} />
        Activar de inmediato
      </label>
      <button type="submit" disabled={!archivo || subiendo} className={claseBotonPrimario}>
        {subiendo ? 'Subiendo…' : 'Subir nueva versión'}
      </button>
      <p className="w-full text-xs text-ink-muted">Solo Word (.docx), máximo {maxMb} MB. La versión anterior se conserva.</p>
    </form>
  )
}

function TarjetaServicio({ servicio, versiones, maxMb, accessToken, ocupado, onActivar, onDescargar, onSubida, onError }) {
  const activa = versiones.find((v) => v.activa)
  const [confirmando, setConfirmando] = useState(null) // id de la versión que se va a activar

  return (
    <section className="bg-surface border border-line rounded-xl p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink-primary">{servicio.nombre}</h2>
        {activa ? (
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-status-signed-bg text-status-signed-fg">
            Versión activa: v{activa.version}
          </span>
        ) : (
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-status-draft-bg text-status-draft-fg">
            Sin plantilla activa
          </span>
        )}
      </div>

      {versiones.length === 0 ? (
        <p className="mt-4 text-sm text-ink-secondary">Todavía no hay versiones. Sube la primera con el botón de abajo.</p>
      ) : (
        <ul className="mt-4 divide-y divide-line">
          {versiones.map((v) => (
            <li key={v.id_plantilla} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink-primary">
                    Versión {v.version}
                    {v.activa && <span className="ml-2 text-xs font-semibold text-status-signed-fg">● Activa</span>}
                  </p>
                  <p className="text-xs text-ink-muted mt-0.5">
                    {formatearFecha(v.fecha_creacion)}
                    {v.subida_por ? ` · ${v.subida_por}` : ''} · {v.nombre_original || 'archivo.docx'} · {formatearTamano(v.tamano_bytes)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => onDescargar(v)} disabled={ocupado} className={claseBotonSecundario}>
                    Descargar
                  </button>
                  {!v.activa &&
                    (confirmando === v.id_plantilla ? (
                      <>
                        <button
                          type="button"
                          onClick={async () => {
                            await onActivar(v)
                            setConfirmando(null)
                          }}
                          disabled={ocupado}
                          className={claseBotonPrimario}
                        >
                          Sí, activar v{v.version}
                        </button>
                        <button type="button" onClick={() => setConfirmando(null)} disabled={ocupado} className="text-sm font-medium text-ink-secondary hover:underline">
                          Cancelar
                        </button>
                      </>
                    ) : (
                      <button type="button" onClick={() => setConfirmando(v.id_plantilla)} disabled={ocupado} className={claseBotonSecundario}>
                        Activar
                      </button>
                    ))}
                </div>
              </div>
              {v.marcas?.length > 0 && (
                <details className="mt-2">
                  <summary className="text-xs text-ink-link cursor-pointer">{v.marcas.length} marcas en esta versión</summary>
                  <p className="mt-1 text-xs text-ink-secondary leading-relaxed">{v.marcas.join(', ')}</p>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}

      <FormularioSubida servicio={servicio} maxMb={maxMb} accessToken={accessToken} onSubida={onSubida} onError={onError} />
    </section>
  )
}

export default function Plantillas() {
  const { accessToken, cerrarSesion } = useAuth()
  const haySesion = Boolean(accessToken)

  const [config, setConfig] = useState(null)
  const [plantillas, setPlantillas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState(false)
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
    ;(async () => {
      try {
        const cfg = await obtenerConfiguracionPlantillas({ accessToken })
        const lista = cfg.puede_gestionar ? await listarPlantillas({ accessToken }) : []
        if (cancelado) return
        setConfig(cfg)
        setPlantillas(lista)
      } catch (e) {
        if (cancelado) return
        const m = mensajeDe(e)
        if (m) setError(m)
      } finally {
        if (!cancelado) setCargando(false)
      }
    })()
    return () => {
      cancelado = true
    }
    // accessToken se renueva solo cada ~85 min; no hace falta recargar por eso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haySesion, recarga])

  async function recargarLista() {
    setPlantillas(await listarPlantillas({ accessToken }))
  }

  function fallo(e) {
    const m = mensajeDe(e)
    if (m) {
      setAviso('')
      setError(m)
    }
  }

  async function alSubir(nueva) {
    setError('')
    try {
      await recargarLista()
      setAviso(`Se guardó la versión ${nueva.version} de «${nueva.nombre_servicio}»${nueva.activa ? ' y quedó activa' : ' (sin activar)'}.`)
    } catch (e) {
      fallo(e)
    }
  }

  async function alActivar(v) {
    setOcupado(true)
    setError('')
    try {
      await activarPlantilla({ accessToken, idPlantilla: v.id_plantilla })
      await recargarLista()
      setAviso(`La versión ${v.version} de «${v.nombre_servicio}» quedó activa.`)
    } catch (e) {
      fallo(e)
    } finally {
      setOcupado(false)
    }
  }

  async function alDescargar(v) {
    setOcupado(true)
    setError('')
    try {
      const blob = await descargarPlantilla({ accessToken, idPlantilla: v.id_plantilla })
      const url = URL.createObjectURL(blob)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `${v.nombre_servicio} v${v.version}.docx`
      document.body.appendChild(enlace)
      enlace.click()
      enlace.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      fallo(e)
    } finally {
      setOcupado(false)
    }
  }

  let contenido
  if (error && !config) {
    contenido = (
      <div role="alert" className="text-center py-10">
        <p className="text-sm text-red-600">{error}</p>
        <button type="button" onClick={() => setRecarga((n) => n + 1)} className="mt-3 text-sm font-medium text-ink-link hover:underline">
          Reintentar
        </button>
      </div>
    )
  } else if (cargando && !config) {
    contenido = <p className="text-sm text-ink-secondary text-center py-10">Cargando plantillas…</p>
  } else if (config && !config.puede_gestionar) {
    contenido = (
      <div className="max-w-xl mx-auto text-center py-16">
        <p className="text-lg font-semibold text-ink-primary">No tienes permiso para gestionar plantillas</p>
        <p className="mt-2 text-sm text-ink-secondary">Si lo necesitas, pídele a un administrador que te dé acceso.</p>
      </div>
    )
  } else if (config) {
    contenido = (
      <div className="max-w-4xl space-y-5">
        <p className="text-sm text-ink-secondary">
          Cada archivo que subes es una versión nueva. Las versiones anteriores se conservan y solo una está activa por servicio:
          esa es la que se usará para generar los documentos.
        </p>

        {aviso && (
          <p role="status" className="text-sm text-status-signed-fg bg-status-signed-bg rounded-lg px-4 py-2.5">
            {aviso}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
            {error}
          </p>
        )}

        {config.servicios.map((s) => (
          <TarjetaServicio
            key={s.id_servicio}
            servicio={s}
            versiones={plantillas.filter((p) => p.id_servicio === s.id_servicio)}
            maxMb={config.max_tamano_mb}
            accessToken={accessToken}
            ocupado={ocupado}
            onActivar={alActivar}
            onDescargar={alDescargar}
            onSubida={alSubir}
            onError={fallo}
          />
        ))}

        <section className="bg-surface border border-line rounded-xl p-5">
          <details>
            <summary className="text-base font-semibold text-ink-primary cursor-pointer">Marcas disponibles ({config.marcas.length})</summary>
            <p className="mt-3 text-sm text-ink-secondary">
              Una marca es el lugar del Word donde el sistema pondrá un dato. Puedes usar campos de combinar correspondencia de Word o
              escribir la marca entre dobles llaves, por ejemplo <code className="text-ink-primary">{'{{RAZON_SOCIAL}}'}</code>. Si el
              archivo trae una marca que no está en esta lista, no se acepta.
            </p>
            <dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
              {config.marcas.map((m) => (
                <div key={m.nombre} className="text-xs">
                  <dt className="inline font-semibold text-ink-primary">{m.nombre}</dt>
                  <dd className="inline text-ink-secondary"> — {m.descripcion}</dd>
                </div>
              ))}
            </dl>
          </details>
        </section>
      </div>
    )
  }

  return <PaginaPanel titulo="Plantillas">{contenido}</PaginaPanel>
}