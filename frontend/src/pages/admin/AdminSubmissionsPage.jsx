import { useCallback, useEffect, useState } from "react";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { extractApiErrorMessage } from "../../utils/apiError";
import { api } from "../../services/api";

const STATUS_FILTERS = ["", "COMPLETED", "IN_PROGRESS", "DRAFT", "ABANDONED"];

const STATUS_STYLES = {
  COMPLETED: "bg-ok-tint text-ok-ink",
  IN_PROGRESS: "bg-accent-tint text-accent-ink",
  DRAFT: "bg-paper text-ink-soft border border-line",
  ABANDONED: "bg-excl-tint text-excl-ink",
};

function formatValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function SubmissionDetail({ submissionId }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/admin/submissions/${submissionId}`)
      .then((response) => setDetail(response.data))
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load submission detail."))
      );
  }, [submissionId]);

  if (error) return <p className="text-sm text-excl-ink mt-2">{error}</p>;
  if (!detail) return <p className="text-sm text-ink-soft mt-2">Loading answers…</p>;
  if (detail.answers.length === 0) {
    return <p className="text-sm text-ink-soft mt-2">No answers saved yet.</p>;
  }

  return (
    <div className="mt-3 border border-line rounded-sm p-4 bg-paper">
      <div className="flex justify-between text-xs text-ink-soft mb-3">
        <span>
          {detail.form_code || "form"} · v{detail.form_version} · {detail.answers.length} answers
        </span>
        <span>
          {detail.completed_at
            ? `Completed ${new Date(detail.completed_at).toLocaleString()}`
            : "Not completed"}
        </span>
      </div>
      <ul className="space-y-2.5">
        {detail.answers.map((answer, index) => (
          <li key={index} className="text-sm">
            <p className="text-ink">{answer.question_text || answer.question_code}</p>
            <p className="text-xs text-ink-soft mt-0.5">
              <span className="font-mono text-ink">{formatValue(answer.value)}</span>
              {answer.source !== "USER_INPUT" && (
                <span className="ml-2 italic">via {answer.source}</span>
              )}
            </p>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-soft italic mt-4">
        Read-only — citizen answers can only be changed by the citizen through
        their own submission flow.
      </p>
    </div>
  );
}

function SubmissionRow({ submission }) {
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-xs px-2 py-0.5 rounded-sm ${STATUS_STYLES[submission.status] || "bg-paper text-ink-soft"}`}
            >
              {submission.status}
            </span>
            <h3 className="text-base text-ink">
              {submission.citizen_name || "Unnamed citizen"}
            </h3>
            <span className="text-xs text-ink-soft font-mono">
              {submission.citizen_id.slice(0, 8)}…
            </span>
          </div>
          <p className="text-xs text-ink-soft mt-1">
            {submission.form_code || "form"} · v{submission.form_version} ·{" "}
            {submission.completion_percentage}% complete · updated{" "}
            {new Date(submission.updated_at).toLocaleString()}
          </p>
        </div>
        <Button size="sm" variant={open ? "secondary" : "ghost"} onClick={() => setOpen((v) => !v)}>
          {open ? "Hide detail" : "View answers"}
        </Button>
      </div>
      {open && <SubmissionDetail submissionId={submission.submission_id} />}
    </Card>
  );
}

export default function AdminSubmissionsPage() {
  const [submissions, setSubmissions] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState("");

  const load = useCallback((status) => {
    api
      .get("/admin/submissions", {
        params: status ? { status } : {},
      })
      .then((response) => setSubmissions(response.data))
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load submissions."))
      );
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  if (error && !submissions) {
    return <ErrorState title="Unable to load submissions" message={error} />;
  }
  if (!submissions) {
    return <LoadingState label="Loading submissions..." />;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-[30px] mb-2">Submissions</h1>
        <p className="max-w-[60ch]">
          Read-only monitoring of citizen form submissions. Answers are shown
          for inspection only — they are never edited from here.
        </p>
      </div>

      <div className="flex gap-2 mb-5 flex-wrap">
        {STATUS_FILTERS.map((status) => (
          <button
            key={status || "all"}
            type="button"
            onClick={() => {
              setStatusFilter(status);
              load(status);
            }}
            className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
              statusFilter === status
                ? "bg-accent text-white border-accent"
                : "bg-transparent text-ink-soft border-line hover:text-ink"
            }`}
          >
            {status || "All"}
          </button>
        ))}
      </div>

      {submissions.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-soft py-2">No submissions match this filter.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {submissions.map((submission) => (
            <SubmissionRow key={submission.submission_id} submission={submission} />
          ))}
        </div>
      )}
    </div>
  );
}
