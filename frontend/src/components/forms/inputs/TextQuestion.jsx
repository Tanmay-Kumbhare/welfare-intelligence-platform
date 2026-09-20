import Input from "../../ui/Input";

/** Text / string questions. */
export default function TextQuestion({ question, value, error, onChange }) {
  return (
    <Input
      id={question.question_id}
      label={question.question_text}
      required={question.required}
      type="text"
      value={value ?? ""}
      placeholder={question.placeholder || undefined}
      error={error}
      hint={question.help_text || undefined}
      maxLength={question.validation_rule?.max_length}
      onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)}
    />
  );
}
