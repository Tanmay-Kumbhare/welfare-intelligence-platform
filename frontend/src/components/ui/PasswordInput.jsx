import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

/**
 * Password input with a show/hide (eye) toggle.
 * Supports an `error` prop for inline validation messages.
 */
export default function PasswordInput({ id, label, hint, error, required, className = "", ...props }) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative mb-5">
      <label htmlFor={id} className="block text-[13px] font-medium text-ink mb-1.5">
        {label}
        {required && <span className="text-excl-ink"> *</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          required={required}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          className={`w-full font-sans text-sm px-3 py-2.5 pr-11 bg-white text-ink border rounded-sm focus:outline-2 focus:outline-accent focus:outline-offset-1 ${
            error ? "border-excl-ink" : "border-line"
          } ${className}`}
          {...props}
        />
        <button
          type="button"
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          onClick={() => setVisible((v) => !v)}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-ink-soft hover:text-ink"
          tabIndex={0}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {hint && !error && <p id={`${id}-hint`} className="text-xs text-ink-soft mt-1">{hint}</p>}
      {error && <p id={`${id}-error`} className="text-[13px] text-excl-ink mt-1.5">{error}</p>}
    </div>
  );
}
