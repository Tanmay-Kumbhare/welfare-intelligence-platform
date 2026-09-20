import { useState } from "react";
import QuestionRenderer from "./QuestionRenderer";
import { validateQuestionValue } from "./formLogic";

/**
 * One dynamic question: merges backend (authoritative) field errors with
 * local definition-driven guidance and forwards typed value changes upward.
 */
export default function FormQuestion({ question, value, onChange, externalError = null }) {
  const [localError, setLocalError] = useState(null);

  const handleChange = (nextValue) => {
    setLocalError(validateQuestionValue(question, nextValue));
    onChange(nextValue);
  };

  return <QuestionRenderer question={question} value={value} error={externalError || localError} onChange={handleChange} />;
}
