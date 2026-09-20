import TextQuestion from "./inputs/TextQuestion";
import TextAreaQuestion from "./inputs/TextAreaQuestion";
import NumberQuestion from "./inputs/NumberQuestion";
import DateQuestion from "./inputs/DateQuestion";
import BooleanQuestion from "./inputs/BooleanQuestion";
import SelectQuestion from "./inputs/SelectQuestion";
import MultiSelectQuestion from "./inputs/MultiSelectQuestion";
import FileQuestion from "./inputs/FileQuestion";

/**
 * Maps a form question definition to its input component. Question types come
 * from the database (see backend QUESTION_TYPES); unknown types fail visible
 * rather than silently dropping the question.
 */
const RENDERERS = {
  text: TextQuestion,
  textarea: TextAreaQuestion,
  number: NumberQuestion,
  decimal: NumberQuestion,
  date: DateQuestion,
  boolean: BooleanQuestion,
  single_choice: SelectQuestion,
  dropdown: SelectQuestion,
  multi_choice: MultiSelectQuestion,
  file: FileQuestion,
};

export default function QuestionRenderer({ question, value, error, onChange }) {
  const Renderer = RENDERERS[(question.question_type || "").toLowerCase()];
  if (!Renderer) {
    return (
      <p className="mb-5 text-[13px] text-excl-ink border border-excl-tint bg-excl-tint px-3 py-2 rounded-sm">
        This question type (&quot;{question.question_type}&quot;) is not yet supported in this app version.
      </p>
    );
  }
  return <Renderer question={question} value={value} error={error} onChange={onChange} />;
}
