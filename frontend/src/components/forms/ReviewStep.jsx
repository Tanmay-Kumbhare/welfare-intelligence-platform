/**
 * Review step: every applicable question and the citizen's answer, grouped
 * by section, with an Edit action per section. Internal identifiers
 * (question IDs, fact codes, profile fields) are never shown.
 */
import Button from "../ui/Button";

function displayValue(question, value) {
  if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    const labels = value.map(
      (code) => question.options?.find((o) => o.option_code === code)?.option_label || code,
    );
    return labels.join(", ");
  }
  if (typeof value === "string" && question.options?.length > 0) {
    return question.options.find((o) => o.option_code === value)?.option_label || value;
  }
  return String(value);
}

export default function ReviewStep({ reviewSections, onEdit }) {
  return (
    <div className="space-y-4">
      {reviewSections.map(({ section, items }, index) => (
        <div key={section.section_id} className="bg-paper-raised border border-line p-[22px]">
          <div className="flex items-start justify-between gap-4 border-b border-line pb-3 mb-3">
            <div>
              <p className="font-mono text-xs text-accent-ink mb-1">
                SECTION {index + 1} OF {reviewSections.length}
              </p>
              <h2 className="text-xl mb-0">{section.section_name}</h2>
            </div>
            <Button type="button" variant="secondary" size="sm" onClick={() => onEdit(index)}>
              Edit
            </Button>
          </div>
          <dl>
            {items.map(({ question, value }) => {
              const display = displayValue(question, value);
              return (
                <div key={question.question_id} className="flex flex-col sm:flex-row sm:justify-between gap-1 py-2 border-b border-line last:border-0">
                  <dt className="text-xs text-ink-soft">{question.question_text}</dt>
                  <dd className={`text-sm sm:text-right ${display === null ? "text-ink-soft italic" : "text-ink"}`}>
                    {display === null ? "Not provided" : display}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      ))}
    </div>
  );
}
