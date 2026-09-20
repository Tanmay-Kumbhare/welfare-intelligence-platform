import Input from "../../ui/Input";

/** Integer and decimal questions (data_type INTEGER / DECIMAL). */
export default function NumberQuestion({ question, value, error, onChange }) {
  const isDecimal = (question.data_type || "").toUpperCase() === "DECIMAL";
  return (
    <Input
      id={question.question_id}
      label={question.question_text}
      required={question.required}
      type="number"
      inputMode={isDecimal ? "decimal" : "numeric"}
      step={isDecimal ? "0.01" : "1"}
      min={question.validation_rule?.min}
      max={question.validation_rule?.max}
      value={value ?? ""}
      placeholder={question.placeholder || undefined}
      error={error}
      hint={question.help_text || undefined}
      onChange={(event) => {
        const raw = event.target.value;
        if (raw === "") return onChange(null);
        const parsed = Number(raw);
        onChange(Number.isFinite(parsed) ? parsed : null);
      }}
    />
  );
}
