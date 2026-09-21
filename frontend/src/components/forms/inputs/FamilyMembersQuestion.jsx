import Button from "../../ui/Button";
import Input from "../../ui/Input";
import Select from "../../ui/Select";

const RELATIONSHIPS = ["SELF", "SPOUSE", "SON", "DAUGHTER", "FATHER", "MOTHER", "OTHER"];

const emptyMember = () => ({ relationship: "", name: "", date_of_birth: "" });

/** A JSON-backed repeating block. Values remain objects until Axios serializes
 * the request body, so the API receives a real JSON array rather than a
 * string that merely resembles JSON. */
export default function FamilyMembersQuestion({ question, value, error, onChange }) {
  const members = Array.isArray(value) ? value : [];
  const changeMember = (index, field, nextValue) => {
    onChange(members.map((member, memberIndex) => (
      memberIndex === index ? { ...member, [field]: nextValue } : member
    )));
  };
  const removeMember = (index) => onChange(members.filter((_, memberIndex) => memberIndex !== index));

  return (
    <fieldset className="mb-5 md:col-span-2" aria-describedby={error ? `${question.question_id}-error` : undefined}>
      <legend className="block text-[13px] font-medium text-ink mb-1.5">{question.question_text}</legend>
      {question.help_text && <p className="text-xs text-ink-soft mb-3">{question.help_text}</p>}
      <div className="space-y-3">
        {members.map((member, index) => (
          <div key={index} className="border border-line rounded-sm p-3 grid md:grid-cols-[1fr_1fr_1fr_auto] gap-x-3 items-start">
            <Select
              id={`${question.question_id}-${index}-relationship`}
              label="Relationship"
              required
              value={member.relationship || ""}
              onChange={(event) => changeMember(index, "relationship", event.target.value)}
            >
              <option value="">Select relationship</option>
              {RELATIONSHIPS.map((relationship) => <option key={relationship} value={relationship}>{relationship}</option>)}
            </Select>
            <Input
              id={`${question.question_id}-${index}-name`}
              label="Name"
              value={member.name || ""}
              onChange={(event) => changeMember(index, "name", event.target.value)}
            />
            <Input
              id={`${question.question_id}-${index}-dob`}
              label="Date of birth"
              type="date"
              value={member.date_of_birth || ""}
              onChange={(event) => changeMember(index, "date_of_birth", event.target.value)}
            />
            <Button type="button" variant="danger" size="sm" className="mt-7" onClick={() => removeMember(index)}>Remove</Button>
          </div>
        ))}
      </div>
      <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...members, emptyMember()])}>Add family member</Button>
      {error && <p id={`${question.question_id}-error`} className="text-[13px] text-excl-ink mt-1.5">{error}</p>}
    </fieldset>
  );
}
