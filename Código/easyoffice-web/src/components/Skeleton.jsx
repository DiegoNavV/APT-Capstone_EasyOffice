// Bloque gris que pulsa, para mostrar mientras llegan datos del servidor. El tamaño se da con `className` (por ejemplo "h-4 w-32").
export function Skeleton({ className = '' }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-gray-200 ${className}`} />
}
