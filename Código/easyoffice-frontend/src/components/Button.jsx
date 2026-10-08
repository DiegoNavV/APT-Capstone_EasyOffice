// Botón principal de los formularios (siempre type="submit").
//
// Props:
// - loading:       true mientras se espera la respuesta del servidor. Desactiva el
//                  botón y muestra `textoCargando` en vez del texto normal.
// - textoCargando: texto a mostrar mientras carga (por defecto "Cargando…").
// - disabled:      desactiva el botón por otra razón (ej. formulario incompleto).
//
// Ojo: `disabled` se saca de props a propósito. Si viniera dentro de `...props`,
// pisaría el `loading || disabled` y el botón podría quedar activo mientras carga
// (permitiendo enviar el formulario dos veces).
export default function Button({
  children,
  loading,
  textoCargando = 'Cargando…',
  disabled,
  className = '',
  ...props
}) {
  return (
    <button
      type="submit"
      className={`w-full flex items-center justify-center gap-2 bg-brand-primary hover:bg-brand-dark disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold px-6 py-3 rounded-[10px] transition-colors ${className}`}
      {...props}
      disabled={loading || disabled}
    >
      {loading ? textoCargando : children}
    </button>
  )
}
