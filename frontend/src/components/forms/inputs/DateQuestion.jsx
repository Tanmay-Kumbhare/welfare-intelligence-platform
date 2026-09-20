import Input from "../../ui/Input";

/** Date questions (data_type DATE, ISO yyyy-mm-dd). */
export default function DateQuestion({ question, value, error, onChange }) {
  return (
    <Input
      id={question.question_id}
      label={question.question_text}
      required={question.required}
      type="date"
      value={value ?? ""}
      error={error}
      hint={question.help_text || undefined}
      onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)}
    />
  );
}
