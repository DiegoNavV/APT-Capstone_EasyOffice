// Chip de estado del listado de trámites (mockup Figma, componente "StatusChip").
// Las claves coinciden con `estado_actual` del backend. Las variantes borrador / enviado / rechazado vienen del mockup y 
// hoy ningún trámite las usa; quedan listas para cuando existan.
const VARIANTES = {
  generado: { bg: 'bg-status-draft-bg', fg: 'text-status-draft-fg', dot: 'bg-ink-secondary', texto: 'Generado' },
  procesando_firma: { bg: 'bg-status-sent-bg', fg: 'text-status-sent-fg', dot: 'bg-status-sent-fg', texto: 'Procesando firma' },
  en_revision: { bg: 'bg-status-sent-bg', fg: 'text-status-sent-fg', dot: 'bg-status-sent-fg', texto: 'En revisión' },
  firmado: { bg: 'bg-status-signed-bg', fg: 'text-status-signed-fg', dot: 'bg-status-signed-fg', texto: 'Firmado' },
  entregado: { bg: 'bg-status-delivered-bg', fg: 'text-status-delivered-fg', dot: 'bg-status-delivered-fg', texto: 'Entregado' },
  borrador: { bg: 'bg-status-draft-bg', fg: 'text-status-draft-fg', dot: 'bg-ink-secondary', texto: 'Borrador' },
  enviado: { bg: 'bg-status-sent-bg', fg: 'text-status-sent-fg', dot: 'bg-status-sent-fg', texto: 'Enviado a firma' },
  rechazado: { bg: 'bg-status-rejected-bg', fg: 'text-status-rejected-fg', dot: 'bg-status-rejected-fg', texto: 'Rechazado' }
}

export default function StatusChip({ variant = 'generado', label }) {
  // Un estado que la vista no conoce se muestra en gris con su propio nombre.
  const v = VARIANTES[variant] ?? { ...VARIANTES.generado, texto: variant }
  return (
    <span className={`inline-flex items-center gap-1.5 pl-2.5 pr-3 py-1 rounded-full ${v.bg}`}>
      <span className={`size-1.5 rounded-full ${v.dot}`} />
      <span className={`text-xs font-semibold tracking-wide ${v.fg}`}>{label ?? v.texto}</span>
    </span>
  )
}