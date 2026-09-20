import FormQuestion from "./FormQuestion";

/** One dynamic section: header + applicable questions, straight from the API. */
export default function FormSection({
  section,
  answers,
  applicable,
  onAnswerChange,
  fieldErrors = new Map(),
  sectionIndex,
  totalSections,
}) {
  const applicableQuestions = section.questions.filter((q) => applicable.get(q.question_id, true));
  return (
    <section aria-labelledby={`section-${section.section_id}`} >
      <div className="border-b border-line pb-4 mb-6">
        <p className="font-mono text-xs text-accent-ink mb-1">
          SECTION {sectionIndex + 1} OF {totalSections}
        </p>
        <h2 id={`section-${section.section_id}`} className="text-2xl mb-1">
          {section.section_name}
        </h2>
        {section.description && <p className="text-sm mb-0">{section.description}</p>}
        {applicableQuestions.length === 0 && (
          <p className="text-sm text-ink-soft mb-0 mt-2">Nothing to fill in this section right now.</p>
        )}
      </div>
      <div className="grid md:grid-cols-2 gap-x-5">
        {applicableQuestions.map((question) => (
          <FormQuestion
            key={question.question_id}
            question={question}
            value={answers.get(question.question_id) ?? null}
            externalError={fieldErrors.get(question.question_id) || null}
            onChange={(value) => onAnswerChange(question, value)}
          />
        ))}
      </div>
    </section>
  );
}
