// Sidebar del panel interno (mockup Figma, pantalla "2 · Listado de trámites").
// "Solicitudes" no está en el mockup original, pero se agregó acá porque es
// una vista real ya construida (solicitud de contacto -> trámite) y este
// sidebar es su único punto de entrada desde que se sacó Panel.jsx.
// "Clientes"/"Plantillas"/"Reportes" sí están en el mockup pero todavía no se
// implementaron, así que no hacen nada al hacer clic.
const ITEMS = [
  { id: 'tramites', label: 'Trámites', href: '/panel/tramites' },
  { id: 'solicitudes', label: 'Solicitudes', href: '/panel/solicitudes' },
  { id: 'clientes', label: 'Clientes' },
  { id: 'plantillas', label: 'Plantillas' },
  { id: 'reportes', label: 'Reportes' }
]

function NavItem({ label, active, href }) {
  const clases = `flex items-center gap-2.5 px-3.5 py-2.5 rounded-md w-full text-sm font-medium transition-colors ${
    active ? 'bg-sidebar-active-bg text-white' : 'text-sidebar-fg hover:text-white cursor-pointer'
  }`
  const icono = <span className={`block rounded-[5px] size-[18px] shrink-0 ${active ? 'bg-white' : 'bg-sidebar-fg'}`} />

  if (href) {
    return (
      <a href={href} className={clases}>
        {icono}
        {label}
      </a>
    )
  }
  // Sección del mockup todavía sin construir: no navega a ningún lado.
  return (
    <button type="button" className={clases} onClick={(e) => e.preventDefault()}>
      {icono}
      {label}
    </button>
  )
}

export default function Sidebar({ activo }) {
  return (
    <aside className="bg-sidebar-bg flex flex-col gap-1.5 h-full shrink-0 w-[244px] px-4 py-[22px]">
      <div className="flex items-center gap-2 pb-[18px] pl-2 pt-1.5">
        <div className="bg-brand-primary flex items-center justify-center rounded-lg size-7 shrink-0">
          <span className="font-bold text-lg text-white">e</span>
        </div>
        <span className="font-bold text-lg text-white">easyoffice</span>
      </div>

      {ITEMS.map((item) => (
        <NavItem key={item.id} label={item.label} href={item.id === activo ? undefined : item.href} active={item.id === activo} />
      ))}

      <div className="flex-1" />

      <NavItem label="Configuración" />
    </aside>
  )
}
