export default function Button({ children, loading, className = '', ...props }) {
  return (
    <button
      type="submit"
      className={`w-full flex items-center justify-center gap-2 bg-brand-primary hover:bg-brand-dark disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold px-6 py-3 rounded-[10px] transition-colors ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? 'Ingresando…' : children}
    </button>
  )
}
