import UserMenu from './UserMenu.jsx'

// Marco de cada vista del panel: encabezado (título, acciones propias de la vista y el menú de usuario, siempre presente) y el área 
// de contenido con scroll. `acciones` es opcional: buscador, botones, etc.
export default function PaginaPanel({ titulo, acciones, children }) {
  return (
    <>
      <header className="bg-surface border-b border-line flex items-center justify-between px-7 py-3.5 shrink-0">
        <h1 className="text-lg font-semibold text-ink-primary">{titulo}</h1>
        <div className="flex items-center gap-3">
          {acciones}
          <UserMenu />
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-7 py-6">{children}</main>
    </>
  )
}