import Select from "../../ui/Select";

const YES_NO = [
  { option_code: "YES", option_label: "Yes" },
  { option_code: "NO", option_label: "No" },
];

/**
 * Boolean questions render as Yes/No — a tri-state: unanswered (empty), yes,
 * no. Several v2 boolean questions (CURRENTLY_STUDYING) also carry YES/NO
 * options in the definition; those are equivalent, so fall back to them if
 * present.
 */
export default function BooleanQuestion({ question, value, error, onChange }) {
  const options = question.options?.length > 0 ? question.options : YES_NO;
  const boolToCode = (v) => (v === true ? "YES" : v === false ? "NO" : "");
  const codeToBool = (code) => (code === "YES" ? true : code === "NO" ? false : null);
  return (
    <Select
      id={question.question_id}
      label={question.question_text}
      required={question.required}
      value={typeof value === "boolean" ? boolToCode(value) : value ?? ""}
      error={error}
      hint={question.help_text || undefined}
      onChange={(event) => {
        const code = event.target.value;
        const configured = options.find((o) => o.option_code === code);
        if (!configured) return onChange(null);
        // Yes/No options map to native booleans; other configured options
        // (none today) pass their code through untouched.
        const mapped = ["YES", "NO"].includes(code) ? codeToBool(code) : code;
        onChange(mapped);
      }}
    >
      <option value="">Please select</option>
      {options.map((option) => (
        <option key={option.option_id || option.option_code} value={option.option_code}>
          {option.option_label}
        </option>
      ))}
    </Select>
  );
}
