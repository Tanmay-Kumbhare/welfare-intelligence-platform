import { useCallback, useEffect, useState } from "react";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { extractApiErrorMessage } from "../../utils/apiError";
import { api } from "../../services/api";

const SOURCE_TYPES = [
  "GOVERNMENT_WEBSITE",
  "GOVERNMENT_PORTAL",
  "GOVERNMENT_API",
  "GOVERNMENT_PDF",
  "OTHER_AUTHORIZED_SOURCE",
];

const RUN_STATUS_STYLES = {
  COMPLETED: "bg-ok-tint text-ok-ink",
  RUNNING: "bg-accent-tint text-accent-ink",
  FAILED: "bg-excl-tint text-excl-ink",
  CANCELLED: "bg-excl-tint text-excl-ink",
};

function RunDetail({ runId }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/admin/ingestion-runs/${runId}`)
      .then((response) => setDetail(response.data))
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load run detail."))
      );
  }, [runId]);

  if (error) return <p className="text-sm text-excl-ink mt-2">{error}</p>;
  if (!detail) return <p className="text-sm text-ink-soft mt-2">Loading snapshot…</p>;

  const latestContent = detail.contents?.[0];

  return (
    <div className="mt-3 border border-line rounded-sm p-4 bg-paper space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div>
          <p className="text-ink-soft">Started</p>
          <p className="text-ink">{new Date(detail.started_at).toLocaleString()}</p>
        </div>
        <div>
          <p className="text-ink-soft">Finished</p>
          <p className="text-ink">
            {detail.completed_at ? new Date(detail.completed_at).toLocaleString() : "—"}
          </p>
        </div>
        <div>
          <p className="text-ink-soft">Documents</p>
          <p className="text-ink">{detail.documents?.length ?? 0}</p>
        </div>
        <div>
          <p className="text-ink-soft">Records created</p>
          <p className="text-ink">{detail.records_created}</p>
        </div>
      </div>

      {(detail.documents || []).map((doc) => (
        <div key={doc.source_document_id} className="text-xs border-t border-line pt-2">
          <p className="text-ink">
            {doc.document_name} <span className="text-ink-soft">v{doc.version}</span>
          </p>
          <p className="text-ink-soft font-mono break-all">
            {doc.document_url}
          </p>
          <p className="text-ink-soft">
            SHA-256: <span className="font-mono text-ink">{doc.content_hash || "—"}</span>
          </p>
        </div>
      ))}

      {detail.error_summary && (
        <p className="text-xs text-excl-ink">{detail.error_summary}</p>
      )}

      {latestContent?.raw_content ? (
        <details>
          <summary className="text-xs text-accent-ink cursor-pointer">
            View raw snapshot ({latestContent.raw_content.length.toLocaleString()} chars)
          </summary>
          <pre className="mt-2 max-h-72 overflow-auto text-[11px] leading-relaxed bg-white border border-line rounded-sm p-3 whitespace-pre-wrap break-all">
            {latestContent.raw_content}
          </pre>
        </details>
      ) : (
        <p className="text-xs text-ink-soft">No raw snapshot stored for this run.</p>
      )}
    </div>
  );
}

function SourceRow({ source, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [showRuns, setShowRuns] = useState(false);
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState({
    source_name: source.source_name,
    source_type: source.source_type,
    base_url: source.base_url || "",
    authority_name: source.authority_name || "",
    status: source.status,
  });

  const triggerFetch = async () => {
    setFetching(true);
    setError("");
    setMessage("");
    try {
      const response = await api.post(`/admin/sources/${source.source_id}/fetch`);
      setLastRun(response.data);
      setMessage(
        response.data.status === "COMPLETED"
          ? `Fetch succeeded — snapshot stored (${response.data.records_created} document).`
          : `Fetch failed: ${response.data.error_summary || "unknown error"}`
      );
      onChanged();
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Fetch request failed."));
    } finally {
      setFetching(false);
    }
  };

  const save = async () => {
    setError("");
    try {
      await api.patch(`/admin/sources/${source.source_id}`, draft);
      setEditing(false);
      onChanged();
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Save failed."));
    }
  };

  const toggleRuns = async () => {
    const next = !showRuns;
    setShowRuns(next);
    if (next && !runs) {
      try {
        const response = await api.get("/admin/ingestion-runs", {
          params: { source_id: source.source_id },
        });
        setRuns(response.data);
      } catch (requestError) {
        setError(extractApiErrorMessage(requestError, "Could not load runs."));
      }
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-lg text-ink">{source.source_name}</h3>
            <span className="text-xs px-2 py-0.5 rounded-sm bg-accent-tint text-accent-ink">
              {source.source_type}
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded-sm ${
                source.status === "ACTIVE"
                  ? "bg-ok-tint text-ok-ink"
                  : "bg-excl-tint text-excl-ink"
              }`}
            >
              {source.status}
            </span>
            {lastRun && (
              <span
                className={`text-xs px-2 py-0.5 rounded-sm ${
                  RUN_STATUS_STYLES[lastRun.status] || "bg-paper text-ink-soft"
                }`}
              >
                last fetch: {lastRun.status}
              </span>
            )}
          </div>
          <p className="text-xs text-ink-soft mt-1 font-mono break-all">
            {source.base_url || "—"}
          </p>
          <p className="text-xs text-ink-soft mt-0.5">
            {source.authority_name || "No authority recorded"} ·{" "}
            {source.document_count} document{source.document_count === 1 ? "" : "s"}
            {source.last_run_status &&
              ` · last run ${source.last_run_status.toLowerCase()}${
                source.last_run_at
                  ? ` ${new Date(source.last_run_at).toLocaleString()}`
                  : ""
              }`}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="primary"
            onClick={triggerFetch}
            disabled={fetching || source.status !== "ACTIVE"}
          >
            {fetching ? "Fetching…" : "Fetch now"}
          </Button>
          <Button size="sm" variant="ghost" onClick={toggleRuns}>
            {showRuns ? "Hide runs" : "Runs"}
          </Button>
          <Button
            size="sm"
            variant={editing ? "secondary" : "ghost"}
            onClick={() => (editing ? save() : setEditing(true))}
          >
            {editing ? "Save" : "Edit"}
          </Button>
        </div>
      </div>

      {message && (
        <p
          className={`text-sm mt-3 ${
            message.startsWith("Fetch failed") ? "text-excl-ink" : "text-ok-ink"
          }`}
        >
          {message}
        </p>
      )}
      {error && <p className="text-sm text-excl-ink mt-3">{error}</p>}

      {editing && (
        <div className="mt-4 grid md:grid-cols-2 gap-x-5">
          <Input
            id={`name-${source.source_id}`}
            label="Source name"
            value={draft.source_name}
            onChange={(e) => setDraft({ ...draft, source_name: e.target.value })}
          />
          <label className="block text-[13px] font-medium text-ink mb-1.5">
            Source type
            <select
              value={draft.source_type}
              onChange={(e) => setDraft({ ...draft, source_type: e.target.value })}
              className="mt-1.5 w-full font-sans text-sm px-3 py-2.5 bg-white text-ink border border-line rounded-sm"
            >
              {SOURCE_TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </label>
          <Input
            id={`url-${source.source_id}`}
            label="Base URL"
            value={draft.base_url}
            onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
          />
          <Input
            id={`authority-${source.source_id}`}
            label="Authority name"
            value={draft.authority_name}
            onChange={(e) => setDraft({ ...draft, authority_name: e.target.value })}
          />
          <label className="block text-[13px] font-medium text-ink mb-1.5">
            Status
            <select
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
              className="mt-1.5 w-full font-sans text-sm px-3 py-2.5 bg-white text-ink border border-line rounded-sm"
            >
              <option value="ACTIVE">ACTIVE</option>
              <option value="INACTIVE">INACTIVE</option>
              <option value="RETIRED">RETIRED</option>
            </select>
          </label>
        </div>
      )}

      {showRuns && (
        <div className="mt-3 space-y-2">
          {runs === null ? (
            <p className="text-sm text-ink-soft">Loading runs…</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-ink-soft">No ingestion runs yet.</p>
          ) : (
            runs.map((run) => (
              <RunRow key={run.ingestion_run_id} run={run} />
            ))
          )}
        </div>
      )}
    </Card>
  );
}

function RunRow({ run }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-line rounded-sm p-3">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`text-xs px-2 py-0.5 rounded-sm ${
            RUN_STATUS_STYLES[run.status] || "bg-paper text-ink-soft"
          }`}
        >
          {run.status}
        </span>
        <span className="text-xs text-ink-soft flex-1">
          {new Date(run.started_at).toLocaleString()}
          {run.records_created > 0 && ` · ${run.records_created} document(s)`}
        </span>
        <span className="text-xs text-accent-ink">{open ? "Hide" : "Detail"}</span>
      </button>
      {run.error_summary && !open && (
        <p className="text-xs text-excl-ink mt-1.5">{run.error_summary}</p>
      )}
      {open && <RunDetail runId={run.ingestion_run_id} />}
    </div>
  );
}

function AddSourceForm({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({
    source_name: "",
    source_type: "GOVERNMENT_WEBSITE",
    base_url: "",
    authority_name: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        + Register source
      </Button>
    );
  }

  const create = async () => {
    setSaving(true);
    setError("");
    try {
      await api.post("/admin/sources", draft);
      setOpen(false);
      onCreated();
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Could not create source."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <h3 className="text-lg text-ink mb-3">Register a scheme source</h3>
      {error && <p className="text-sm text-excl-ink mb-3">{error}</p>}
      <div className="grid md:grid-cols-2 gap-x-5">
        <Input
          id="new-source-name"
          label="Source name"
          value={draft.source_name}
          onChange={(e) => setDraft({ ...draft, source_name: e.target.value })}
        />
        <label className="block text-[13px] font-medium text-ink mb-1.5">
          Source type
          <select
            value={draft.source_type}
            onChange={(e) => setDraft({ ...draft, source_type: e.target.value })}
            className="mt-1.5 w-full font-sans text-sm px-3 py-2.5 bg-white text-ink border border-line rounded-sm"
          >
            {SOURCE_TYPES.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </label>
        <Input
          id="new-source-url"
          label="Base URL (https://…)"
          value={draft.base_url}
          onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
        />
        <Input
          id="new-source-authority"
          label="Authority name"
          value={draft.authority_name}
          onChange={(e) => setDraft({ ...draft, authority_name: e.target.value })}
        />
      </div>
      <div className="flex gap-2 mt-4">
        <Button onClick={create} disabled={saving || !draft.source_name || !draft.base_url}>
          {saving ? "Creating…" : "Create source"}
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </Card>
  );
}

export default function AdminSourcesPage() {
  const [sources, setSources] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .get("/admin/sources")
      .then((response) => setSources(response.data))
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load sources."))
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !sources) {
    return <ErrorState title="Unable to load sources" message={error} />;
  }
  if (!sources) {
    return <LoadingState label="Loading sources..." />;
  }

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[30px] mb-2">Sources</h1>
          <p className="max-w-[60ch]">
            Authoritative government sources for scheme information. Fetching
            stores a verbatim raw snapshot with a SHA-256 hash for provenance —
            it never modifies published scheme rules.
          </p>
        </div>
        <AddSourceForm onCreated={load} />
      </div>

      <div className="space-y-4">
        {sources.length === 0 ? (
          <Card>
            <p className="text-sm text-ink-soft py-2">
              No sources registered yet. Register one to start ingesting.
            </p>
          </Card>
        ) : (
          sources.map((source) => (
            <SourceRow key={source.source_id} source={source} onChanged={load} />
          ))
        )}
      </div>
    </div>
  );
}
