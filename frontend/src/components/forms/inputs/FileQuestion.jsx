import { FileText } from "lucide-react";

/**
 * File questions: the document store does not exist yet (future phase), so
 * these render as a clear, non-blocking notice. Their answers are not sent to
 * the backend — the question remains unanswered rather than faking a value.
 */
export default function FileQuestion({ question }) {
  return (
    <div className="mb-5 border border-line bg-paper px-3 py-3 rounded-sm">
      <p className="text-[13px] font-medium text-ink mb-1">
        {question.question_text}
        {question.required && <span className="text-excl-ink"> *</span>}
      </p>
      <p className="text-xs text-ink-soft flex items-start gap-1.5 mb-0">
        <FileText className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden="true" />
        Document upload will be available in a future update. You can continue without it for now.
      </p>
    </div>
  );
}
