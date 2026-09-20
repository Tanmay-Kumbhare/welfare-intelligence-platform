import Select from "../../ui/Select";

/** Single-choice and dropdown questions backed by configured options. */
export default function SelectQuestion({ question, value, error, onChange }) {
  return (
    <Select
      id={question.question_id}
      label={question.question_text}
      required={question.required}
      value={value ?? ""}
      error={error}
      hint={question.help_text || undefined}
      onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)}
    >
      <option value="">Please select</option>
      {(question.options || []).map((option) => (
        <option key={option.option_id} value={option.option_code}>
          {option.option_label}
        </option>
      ))}
    </Select>
  );
}
