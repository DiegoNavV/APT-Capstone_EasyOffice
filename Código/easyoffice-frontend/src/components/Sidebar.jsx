import { NavLink } from 'react-router-dom'

// Sidebar del panel interno (mockup Figma, pantalla "2 · Listado de trámites").
// "Solicitudes" no está en el mockup original, pero se agregó acá porque es una vista real ya construida (solicitud de contacto -> trámite).
// Las secciones que todavía no se desarrollan (Configuración) sí navegan, pero muestran "Próximamente"
// (ver Proximamente.jsx y las rutas en App.jsx); a medida que se construyan, se activan en App.jsx.
// Reportes navega siempre (no se oculta para agentes): el backend decide con `puede_ver` si se le muestran los datos o un aviso.
// Cerrar sesión no va acá: está en el menú desplegable del avatar (UserMenu).
const ITEMS = [
  { id: 'tramites', label: 'Trámites', href: '/panel/tramites' },
  { id: 'solicitudes', label: 'Solicitudes', href: '/panel/solicitudes' },
  { id: 'clientes', label: 'Clientes', href: '/panel/clientes' },
  { id: 'plantillas', label: 'Plantillas', href: '/panel/plantillas' },
  { id: 'reportes', label: 'Reportes', href: '/panel/reportes' }
]

const CLASES_BASE = 'flex items-center gap-2.5 px-3.5 py-2.5 rounded-md w-full text-sm font-medium transition-colors'

function Icono({ activo }) {
  return <span className={`block rounded-[5px] size-[18px] shrink-0 ${activo ? 'bg-white' : 'bg-sidebar-fg'}`} />
}

// NavLink marca solo cuál es la página actual (isActive); no hace falta que
// cada vista le diga al Sidebar dónde está.
function NavItem({ label, href }) {
  return (
    <NavLink
      to={href}
      className={({ isActive }) =>
        `${CLASES_BASE} ${isActive ? 'bg-sidebar-active-bg text-white' : 'text-sidebar-fg hover:text-white cursor-pointer'}`
      }
    >
      {({ isActive }) => (
        <>
          <Icono activo={isActive} />
          {label}
        </>
      )}
    </NavLink>
  )
}

export default function Sidebar() {
  return (
    <aside className="bg-sidebar-bg flex flex-col gap-1.5 h-full shrink-0 w-[244px] px-4 py-[22px]">
      <div className="flex items-center gap-2 pb-[18px] pl-2 pt-1.5">
        <div className="bg-brand-primary flex items-center justify-center rounded-lg size-7 shrink-0">
          <span className="font-bold text-lg text-white">e</span>
        </div>
        <span className="font-bold text-lg text-white">easyoffice</span>
      </div>

      {ITEMS.map((item) => (
        <NavItem key={item.id} label={item.label} href={item.href} />
      ))}

      <div className="flex-1" />

      <NavItem label="Configuración" href="/panel/configuracion" />
    </aside>
  )
}