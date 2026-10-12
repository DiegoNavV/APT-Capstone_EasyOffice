import PaginaPanel from './PaginaPanel.jsx'

// Pantalla de relleno para las secciones del menú que todavía no se desarrollan. Cuando una se construya, en App.jsx se cambia esta pantalla
// por la vista real.
export default function Proximamente({ titulo }) {
  return (
    <PaginaPanel titulo={titulo}>
      <div className="h-full flex flex-col items-center justify-center text-center">
        <p className="text-2xl font-semibold text-ink-primary">Próximamente</p>
        <p className="mt-2 text-sm text-ink-muted">La sección {titulo} todavía no está disponible.</p>
      </div>
    </PaginaPanel>
  )
}