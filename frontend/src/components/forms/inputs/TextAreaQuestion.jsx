import Input from "../../ui/Input";

/**
 * TextArea questions render as multi-line text. The backend stores them as
 * STRING with optional min/max_length validation; v2 uses this for structured
 * repeating data (e.g. FAMILY_MEMBERS JSON entry) pending a dedicated
 * repeating-group UI in a later phase.
 */
export default function TextAreaQuestion({ question, value, error, onChange }) {
  return (
    <div className="mb-5">
      <label htmlFor={question.question_id} className="block text-[13px] font-medium text-ink mb-1.5">
        {question.question_text}
        {question.required && <span className="text-excl-ink"> *</span>}
      </label>
      <textarea
        id={question.question_id}
        rows={3}
        className={`w-full font-sans text-sm px-3 py-2.5 bg-white text-ink border rounded-sm focus:outline-2 focus:outline-accent focus:outline-offset-1 ${
          error ? "border-excl-ink" : "border-line"
        }`}
        aria-invalid={!!error}
        aria-describedby={error ? `${question.question_id}-error` : question.help_text ? `${question.question_id}-hint` : undefined}
        placeholder={question.placeholder || undefined}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)}
      />
      {question.help_text && !error && (
        <p id={`${question.question_id}-hint`} className="text-xs text-ink-soft mt-1">
          {question.help_text}
        </p>
      )}
      {error && (
        <p id={`${question.question_id}-error`} className="text-[13px] text-excl-ink mt-1.5">
          {error}
        </p>
      )}
    </div>
  );
}
