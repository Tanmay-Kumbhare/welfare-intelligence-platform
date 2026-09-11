export default function Input({
  label,
  hint,
  error,
  id,
  className = "",
  required,
  ...props
}) {
  return (
    <div className={`mb-5 ${error ? "" : ""}`}>
      {label && (
        <label htmlFor={id} className="block text-[13px] font-medium text-ink mb-1.5">
          {label}
          {required && <span className="text-excl-ink"> *</span>}
        </label>
      )}
      <input
        id={id}
        className={`w-full font-sans text-sm px-3 py-2.5 bg-white text-ink border rounded-sm focus:outline-2 focus:outline-accent focus:outline-offset-1 ${
          error ? "border-excl-ink" : "border-line"
        } ${className}`}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        {...props}
      />
      {hint && !error && (
        <p id={`${id}-hint`} className="text-xs text-ink-soft mt-1">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-[13px] text-excl-ink mt-1.5">
          {error}
        </p>
      )}
    </div>
  );
}
