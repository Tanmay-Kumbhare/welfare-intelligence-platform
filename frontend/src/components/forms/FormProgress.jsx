import { Check } from "lucide-react";

/**
 * Progress header: current step, per-section status dots, and the
 * backend-reported completion percentage (over applicable questions).
 */
export default function FormProgress({ sections, currentStep, applicable, answers, completionPercentage }) {
  const dotState = (section) => {
    const qs = section.questions.filter((q) => applicable.get(q.question_id, true));
    const answered = qs.filter((q) => isAnswered(answers.get(q.question_id))).length;
    if (qs.length === 0) return "empty";
    if (answered === 0) return "pending";
    if (answered === qs.length) return "complete";
    return "partial";
  };

  return (
    <div className="mb-7">
      <div className="flex items-center gap-2 text-xs font-mono text-ink-soft" aria-label={`Step ${currentStep + 1} of ${sections.length}`}>
        <span>
          STEP {currentStep + 1} OF {sections.length}
        </span>
        <div className="flex-1 h-1 bg-line max-w-65" aria-hidden="true">
          <div className="h-1 bg-accent transition-all" style={{ width: `${completionPercentage}%` }} />
        </div>
        <span className="text-ink">{completionPercentage}% complete</span>
      </div>
      <ol className="flex flex-wrap gap-x-1 gap-y-1 mt-4" aria-hidden="true">
        {sections.map((section, index) => {
          const state = dotState(section);
          return (
            <li
              key={section.section_id}
              className={`text-[11px] font-mono px-2 py-1 rounded-sm border ${
                index === currentStep
                  ? "border-accent text-accent-ink bg-accent-tint"
                  : state === "complete"
                    ? "border-line text-ok-ink bg-ok-tint"
                    : "border-line text-ink-soft bg-transparent"
              }`}
            >
              {state === "complete" && index !== currentStep ? <Check className="h-3 w-3 inline" aria-hidden="true" /> : null}
              {section.section_name}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function isAnswered(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  if (Array.isArray(value) && value.length === 0) return false;
  return true;
}
