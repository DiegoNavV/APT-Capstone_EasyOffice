import { useEffect, useState } from 'react'
import { useAuth } from '../lib/AuthContext.jsx'
import { ApiError } from '../lib/api.js'
import { descargarInformeTramites, obtenerReporteTramites } from '../lib/tramitesApi.js'
import PaginaPanel from '../components/PaginaPanel.jsx'
import StatusChip from '../components/StatusChip.jsx'
import { SkeletonTarjeta } from '../components/Skeleton.jsx'

// Vista "Reportes" del panel (mockup Figma, pantalla "9 · Exportar reporte"), con los conteos agregados reales de
// GET /api/tramites/reporte. Exclusiva de administradores -- confirmado con el cliente (ver
// Resumen_Alcance_Proyecto_EasyOffice.docx: "panel de resumen" es una función exclusiva del administrador), por eso
// el backend decide con `puede_ver` en vez de ocultar el link en el Sidebar.
// "Descargar datos" abre un popup para elegir CSV y/o PDF (uno, otro o ambos) antes de iniciar la descarga.
// El CSV se arma en el cliente con los mismos datos ya cargados (sin pedirlos de nuevo al backend); el PDF lo
// genera el backend (GET /api/tramites/reporte/informe, ver app/informe_tramites.py). Exportar a Word (como en
// el mockup) todavía no está construido.

// Necesario al inicio del archivo CSV para que Excel en Windows detecte UTF-8 y no
// corrompa las tildes (ej. "Autorización") al abrirlo con doble clic.
const BOM_UTF8 = '﻿'

// Escapa un valor para CSV: lo entrecomilla si tiene coma, comilla o salto de línea.
function csv(valor) {
  const texto = String(valor ?? '')
  return /[",\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto
}

function seccionACsv(titulo, etiquetaColumna, filas) {
  const lineasFilas = filas.map((f) => [csv(f.etiqueta), f.cantidad].join(','))
  return [titulo, [etiquetaColumna, 'Cantidad'].join(','), ...lineasFilas].join('\n')
}

function reporteACsv(datos) {
  return [
    `Total de trámites,${datos.total}`,
    '',
    seccionACsv('Por estado', 'Estado', datos.por_estado),
    '',
    seccionACsv('Por servicio', 'Servicio', datos.por_servicio),
    '',
    seccionACsv('Por agente', 'Agente', datos.por_agente)
  ].join('\n')
}

// Nombre con la fecha de hoy, igual para el CSV y el PDF.
function nombreArchivo(extension) {
  return `reporte-tramites-${new Date().toISOString().slice(0, 10)}.${extension}`
}

// Dispara la descarga de un Blob ya en memoria -- no navega la página, solo crea y hace clic en un
// <a download> temporal (mismo patrón que descargarPdf en ClienteDetalle.jsx/Tramites.jsx).
function descargarBlob(blob, nombre) {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}

// Popup para elegir en qué formato(s) descargar el reporte. Controlado por el padre: no sabe nada
// de la API, solo junta la selección y la entrega al confirmar.
function ModalDescarga({ quiereCsv, quierePdf, onCambiarCsv, onCambiarPdf, descargando, error, onCancelar, onConfirmar }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Descargar datos"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !descargando) onCancelar()
      }}
    >
      <div className="w-full max-w-sm bg-surface border border-line rounded-[10px] p-5 shadow-lg">
        <p className="text-base font-semibold text-ink-primary">Descargar datos</p>
        <p className="mt-1 text-sm text-ink-secondary">Elige en qué formato quieres el reporte. Puedes elegir uno o ambos.</p>

        <div className="mt-4 space-y-2.5">
          <label className="flex items-center gap-2 text-sm text-ink-primary">
            <input type="checkbox" checked={quiereCsv} onChange={(e) => onCambiarCsv(e.target.checked)} disabled={descargando} />
            CSV (Excel)
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-primary">
            <input type="checkbox" checked={quierePdf} onChange={(e) => onCambiarPdf(e.target.checked)} disabled={descargando} />
            PDF
          </label>
        </div>

        {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancelar}
            disabled={descargando}
            className="text-sm font-medium text-ink-primary bg-surface border border-line-strong hover:border-ink-muted disabled:opacity-60 px-4 py-2 rounded-[10px] transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirmar}
            disabled={descargando || (!quiereCsv && !quierePdf)}
            className="text-sm font-semibold text-white bg-brand-primary hover:bg-brand-dark disabled:opacity-60 px-4 py-2 rounded-[10px] transition-colors"
          >
            {descargando ? 'Descargando…' : 'Descargar'}
          </button>
        </div>
      </div>
    </div>
  )
}

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

  const [modalAbierto, setModalAbierto] = useState(false)
  const [quiereCsv, setQuiereCsv] = useState(true)
  const [quierePdf, setQuierePdf] = useState(true)
  const [descargando, setDescargando] = useState(false)
  const [errorDescarga, setErrorDescarga] = useState('')

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

  // El botón ya está oculto para quien no es administrador (ver `acciones`), pero se repite el
  // chequeo acá por si alguien igual llega a invocar la función (ej. desde la consola).
  function abrirModalDescarga() {
    if (!datos?.puede_ver) {
      window.alert('No tienes permiso para exportar este reporte.')
      return
    }
    setErrorDescarga('')
    setModalAbierto(true)
  }

  function cerrarModalDescarga() {
    if (descargando) return
    setModalAbierto(false)
  }

  // El CSV se arma con lo que ya está en `datos` (sin volver a pedirle nada al backend); el PDF lo
  // genera el backend. Si el usuario eligió ambos, el CSV sale de inmediato y luego se espera el PDF
  // -- así un PDF lento no retrasa la descarga del CSV.
  async function confirmarDescarga() {
    setErrorDescarga('')
    setDescargando(true)
    try {
      if (quiereCsv) {
        descargarBlob(new Blob([BOM_UTF8 + reporteACsv(datos)], { type: 'text/csv;charset=utf-8' }), nombreArchivo('csv'))
      }
      if (quierePdf) {
        const blob = await descargarInformeTramites({ accessToken })
        descargarBlob(blob, nombreArchivo('pdf'))
      }
      setModalAbierto(false)
    } catch (e) {
      const m = mensajeDe(e)
      if (m) setErrorDescarga(m)
    } finally {
      setDescargando(false)
    }
  }

  const acciones = (
    <div className="flex items-center gap-2">
      {datos && datos.puede_ver && datos.total > 0 && (
        <button
          type="button"
          onClick={abrirModalDescarga}
          className="text-sm font-medium text-ink-primary bg-surface border border-line-strong hover:border-ink-muted px-4 py-2.5 rounded-[10px] transition-colors"
        >
          Generar Informe
        </button>
      )}
      <button
        type="button"
        onClick={() => setRecarga((n) => n + 1)}
        disabled={cargando}
        className="text-sm font-medium text-ink-primary bg-surface border border-line-strong hover:border-ink-muted disabled:opacity-60 px-4 py-2.5 rounded-[10px] transition-colors"
      >
        Actualizar
      </button>
    </div>
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
    contenido = (
      <div className="max-w-6xl space-y-5">
        <div className="w-64">
          <SkeletonTarjeta lineas={1} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SkeletonTarjeta />
          <SkeletonTarjeta />
          <SkeletonTarjeta />
        </div>
      </div>
    )
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

  return (
    <PaginaPanel titulo="Reportes" acciones={acciones}>
      {contenido}
      {modalAbierto && (
        <ModalDescarga
          quiereCsv={quiereCsv}
          quierePdf={quierePdf}
          onCambiarCsv={setQuiereCsv}
          onCambiarPdf={setQuierePdf}
          descargando={descargando}
          error={errorDescarga}
          onCancelar={cerrarModalDescarga}
          onConfirmar={confirmarDescarga}
        />
      )}
    </PaginaPanel>
  )
}
