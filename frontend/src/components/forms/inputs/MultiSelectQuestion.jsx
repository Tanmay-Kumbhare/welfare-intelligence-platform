import Select from "../../ui/Select";

/**
 * Multi-choice questions: list of option codes. v2 has no multi_choice
 * questions today, but the renderer supports the type per the form spec so a
 * future definition needs no frontend change.
 */
export default function MultiSelectQuestion({ question, value, error, onChange }) {
  const selected = Array.isArray(value) ? value : [];
  const toggle = (code) => {
    const next = selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code];
    onChange(next.length > 0 ? next : null);
  };
  return (
    <fieldset id={question.question_id} className="mb-5">
      <legend className="block text-[13px] font-medium text-ink mb-1.5">
        {question.question_text}
        {question.required && <span className="text-excl-ink"> *</span>}
      </legend>
      <div
        className={`border rounded-sm bg-white p-3 ${error ? "border-excl-ink" : "border-line"}`}
        aria-invalid={!!error}
      >
        {(question.options || []).map((option) => (
          <label key={option.option_id} className="flex items-center gap-2 py-1 text-sm text-ink cursor-pointer">
            <input
              type="checkbox"
              checked={selected.includes(option.option_code)}
              onChange={() => toggle(option.option_code)}
              aria-describedby={error ? `${question.question_id}-error` : undefined}
            />
            {option.option_label}
          </label>
        ))}
      </div>
      {question.help_text && !error && <p className="text-xs text-ink-soft mt-1">{question.help_text}</p>}
      {error && (
        <p id={`${question.question_id}-error`} className="text-[13px] text-excl-ink mt-1.5">
          {error}
        </p>
      )}
    </fieldset>
  );
}
