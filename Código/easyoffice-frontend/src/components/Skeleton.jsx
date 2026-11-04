// Bloques de carga del panel: se muestran en lugar del contenido mientras llegan los datos.
// Usan los mismos colores y medidas que las tablas y tarjetas reales, para que la página no "salte" al cargar.

// Un bloque gris que pulsa. El tamaño se da con `className` (por ejemplo "h-4 w-32").
export function Skeleton({ className = '' }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-line ${className}`} />
}

// Filas de una tabla. `columnas` repite los anchos de las columnas reales (por ejemplo ['flex-1', 'w-[230px]']),
// para que cada bloque quede bajo su encabezado. Si el ancho trae "text-right", el bloque va pegado a la derecha.
export function SkeletonFilas({ filas = 5, columnas }) {
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">Cargando...</span>
      {Array.from({ length: filas }, (_, i) => (
        <div key={i} className="border-b border-line last:border-b-0 flex items-center px-4 py-[13px]">
          {columnas.map((ancho, j) => {
            const aLaDerecha = ancho.includes('text-right')
            return (
              <div key={j} className={`${ancho} ${aLaDerecha ? 'pl-4' : 'pr-4'}`}>
                <Skeleton className={`${j === 0 ? 'h-4 w-3/4' : 'h-4 w-2/3'} ${aLaDerecha ? 'ml-auto' : ''}`} />
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// Tarjetas de cifras, como los contadores de la parte superior de Trámites.
export function SkeletonTarjetas({ cantidad = 4 }) {
  return (
    <div role="status" aria-busy="true" className="flex gap-4">
      <span className="sr-only">Cargando...</span>
      {Array.from({ length: cantidad }, (_, i) => (
        <div key={i} className="bg-surface border border-line rounded-[10px] flex-1 px-5 py-[18px]">
          <Skeleton className="h-3.5 w-28" />
          <Skeleton className="mt-3 h-7 w-12" />
          <Skeleton className="mt-3 h-3 w-40" />
        </div>
      ))}
    </div>
  )
}

// Una tarjeta con varias líneas de texto, para fichas y paneles sueltos.
export function SkeletonTarjeta({ lineas = 4 }) {
  return (
    <div role="status" aria-busy="true" className="bg-surface border border-line rounded-[10px] p-5">
      <span className="sr-only">Cargando...</span>
      <Skeleton className="h-5 w-48" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: lineas }, (_, i) => (
          <Skeleton key={i} className={`h-3.5 ${i % 2 === 0 ? 'w-full' : 'w-2/3'}`} />
        ))}
      </div>
    </div>
  )
}