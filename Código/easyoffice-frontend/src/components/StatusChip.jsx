// Chip de estado del listado de trámites (mockup Figma, componente "StatusChip").
const VARIANTES = {
  borrador: { bg: 'bg-status-draft-bg', fg: 'text-status-draft-fg', dot: 'bg-ink-secondary', texto: 'Borrador' },
  enviado: { bg: 'bg-status-sent-bg', fg: 'text-status-sent-fg', dot: 'bg-status-sent-fg', texto: 'Enviado a firma' },
  firmado: { bg: 'bg-status-signed-bg', fg: 'text-status-signed-fg', dot: 'bg-status-signed-fg', texto: 'Firmado' },
  entregado: { bg: 'bg-status-delivered-bg', fg: 'text-status-delivered-fg', dot: 'bg-status-delivered-fg', texto: 'Entregado' },
  rechazado: { bg: 'bg-status-rejected-bg', fg: 'text-status-rejected-fg', dot: 'bg-status-rejected-fg', texto: 'Rechazado' }
}

export default function StatusChip({ variant = 'borrador', label }) {
  const v = VARIANTES[variant] ?? VARIANTES.borrador
  return (
    <span className={`inline-flex items-center gap-1.5 pl-2.5 pr-3 py-1 rounded-full ${v.bg}`}>
      <span className={`size-1.5 rounded-full ${v.dot}`} />
      <span className={`text-xs font-semibold tracking-wide ${v.fg}`}>{label ?? v.texto}</span>
    </span>
  )
}
