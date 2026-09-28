import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

/**
 * Password input with a show/hide (eye) toggle.
 * Forwards everything else to the shared <Input /> component.
 */
export default function PasswordInput({ id, label, hint, required, className = "", ...props }) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <label htmlFor={id} className="block text-[13px] font-medium text-ink mb-1.5">
        {label}
        {required && <span className="text-excl-ink"> *</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          required={required}
          className={`w-full font-sans text-sm px-3 py-2.5 pr-11 bg-white text-ink border border-line rounded-sm focus:outline-2 focus:outline-accent focus:outline-offset-1 ${className}`}
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
      {hint && <p className="text-xs text-ink-soft mt-1">{hint}</p>}
    </div>
  );
}
