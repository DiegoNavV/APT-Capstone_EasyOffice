export default function TextField({ label, id, error, ...props }) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1.5 w-full">
      <span className="text-[13px] font-medium text-ink-secondary">{label}</span>
      <input
        id={id}
        className={`w-full bg-surface border rounded-md px-3.5 py-3 text-sm text-ink-primary outline-none transition-colors
          ${error ? 'border-red-400 focus:border-red-500' : 'border-line focus:border-brand-primary'}`}
        {...props}
      />
      {error && <span className="text-xs text-red-600">{error}</span>}
    </label>
  )
}
