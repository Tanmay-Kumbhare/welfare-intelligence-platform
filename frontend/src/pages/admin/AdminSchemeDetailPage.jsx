import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Select from "../../components/ui/Select";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import ConfirmDialog from "../../components/admin/ConfirmDialog";
import useAdminDraft from "../../components/admin/useAdminDraft";
import { extractApiErrorMessage } from "../../utils/apiError";
import { adminService } from "../../services/api";
import {
  APPLICATION_WINDOW_TYPES,
  SCHEME_CATEGORIES,
  SCHEME_PERSONAS,
  SCHEME_SOURCE_TYPES,
  SCHEME_STATUSES,
} from "../../components/admin/rulesVocabulary";
import RuleManager from "../../components/admin/RuleManager";
import DocumentManager from "../../components/admin/DocumentManager";
import SourceLinkPanel from "../../components/admin/SourceLinkPanel";
import VerificationPanel from "../../components/admin/VerificationPanel";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "rules", label: "Eligibility rules" },
  { key: "documents", label: "Required documents" },
  { key: "sources", label: "Sources / provenance" },
  { key: "verification", label: "Verification" },
];

function isoOrNull(value) {
  return value ? String(value).slice(0, 10) : "";
}

function MetaEditForm({ scheme, onSaved, onCancel }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedNotice, setSavedNotice] = useState("");

  // All fields the backend PATCH accepts. Deliberately ABSENT:
  // group_combining_operator (reviewed decision in the Rules tab),
  // last_verified_at (only the Verification tab sets it).
  const { fields, setField, dirty, reset } = useAdminDraft({
    scheme_name: scheme.scheme_name || "",
    department_name: scheme.department_name || "",
    scheme_category: scheme.scheme_category || "",
    target_persona: scheme.target_persona || "",
    description: scheme.description || "",
    benefit_description: scheme.benefit_description || "",
    status: scheme.status || "ACTIVE",
    start_date: isoOrNull(scheme.start_date),
    end_date: isoOrNull(scheme.end_date),
    official_source_url: scheme.official_source_url || "",
    application_url: scheme.application_url || "",
    application_window_type: scheme.application_window_type || "",
    official_scheme_identifier: scheme.official_scheme_identifier || "",
    source_type: scheme.source_type || "",
    source_name: scheme.source_name || "",
    source_url: scheme.source_url || "",
  });

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSavedNotice("");
    // Explicit PATCH-only mutation; this NEVER touches verification state —
    // the backend enforces that distinction, and the UI reinforces it here.
    // Empty strings are omitted: the backend parses empty optional dates/URLs
    // as invalid values, while an absent key means "no change".
    const payload = {};
    for (const [key, value] of Object.entries(fields)) {
      if (value !== "") payload[key] = value;
    }
    try {
      await adminService.updateScheme(scheme.scheme_id, payload);
      setSavedNotice("Saved. This was metadata only — the scheme was NOT verified.");
      onSaved();
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Save failed."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="mt-4 border border-line rounded-sm p-4 bg-paper-raised">
      <h3 className="text-lg text-ink mb-3">Edit metadata</h3>
      {savedNotice && <p className="text-sm text-ok-ink mb-3">{savedNotice}</p>}
      {error && <p className="text-sm text-excl-ink mb-3">{error}</p>}
      <div className="grid md:grid-cols-2 gap-x-5">
        <Input
          id="edit-scheme-name"
          label="Scheme name"
          required
          value={fields.scheme_name}
          onChange={(e) => setField("scheme_name", e.target.value)}
        />
        <Input
          id="edit-scheme-department"
          label="Department"
          value={fields.department_name}
          onChange={(e) => setField("department_name", e.target.value)}
        />
        <Select
          id="edit-scheme-category"
          label="Category"
          value={fields.scheme_category}
          onChange={(e) => setField("scheme_category", e.target.value)}
        >
          <option value="">— none —</option>
          {SCHEME_CATEGORIES.map((category) => (
            <option key={category} value={category}>{category}</option>
          ))}
        </Select>
        <Select
          id="edit-scheme-persona"
          label="Target persona"
          value={fields.target_persona}
          onChange={(e) => setField("target_persona", e.target.value)}
        >
          <option value="">— none —</option>
          {SCHEME_PERSONAS.map((persona) => (
            <option key={persona} value={persona}>{persona}</option>
          ))}
        </Select>
        <div className="md:col-span-2">
          <Input
            id="edit-scheme-description"
            label="Description"
            value={fields.description}
            onChange={(e) => setField("description", e.target.value)}
          />
        </div>
        <div className="md:col-span-2">
          <Input
            id="edit-scheme-benefit"
            label="Benefit description"
            value={fields.benefit_description}
            onChange={(e) => setField("benefit_description", e.target.value)}
          />
        </div>
        <Select
          id="edit-scheme-status"
          label="Status"
          hint="Archive/restore is also available as a dedicated action"
          value={fields.status}
          onChange={(e) => setField("status", e.target.value)}
        >
          {SCHEME_STATUSES.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </Select>
        <Select
          id="edit-scheme-window"
          label="Application window type"
          value={fields.application_window_type}
          onChange={(e) => setField("application_window_type", e.target.value)}
        >
          <option value="">— not specified —</option>
          {APPLICATION_WINDOW_TYPES.map((windowType) => (
            <option key={windowType} value={windowType}>{windowType}</option>
          ))}
        </Select>
        <Input
          id="edit-scheme-start"
          label="Start date"
          type="date"
          value={fields.start_date}
          onChange={(e) => setField("start_date", e.target.value)}
        />
        <Input
          id="edit-scheme-end"
          label="End date"
          type="date"
          value={fields.end_date}
          onChange={(e) => setField("end_date", e.target.value)}
        />
        <Input
          id="edit-scheme-official-url"
          label="Official source URL"
          type="url"
          value={fields.official_source_url}
          onChange={(e) => setField("official_source_url", e.target.value)}
        />
        <Input
          id="edit-scheme-apply-url"
          label="Application URL"
          type="url"
          value={fields.application_url}
          onChange={(e) => setField("application_url", e.target.value)}
        />
        <Input
          id="edit-scheme-identifier"
          label="Official scheme identifier"
          value={fields.official_scheme_identifier}
          onChange={(e) => setField("official_scheme_identifier", e.target.value)}
        />
        <Select
          id="edit-scheme-source-type"
          label="Source type (provenance)"
          value={fields.source_type}
          onChange={(e) => setField("source_type", e.target.value)}
        >
          <option value="">— none —</option>
          {SCHEME_SOURCE_TYPES.map((sourceType) => (
            <option key={sourceType} value={sourceType}>{sourceType}</option>
          ))}
        </Select>
        <Input
          id="edit-scheme-source-name"
          label="Source name"
          value={fields.source_name}
          onChange={(e) => setField("source_name", e.target.value)}
        />
        <Input
          id="edit-scheme-source-url"
          label="Source URL"
          type="url"
          value={fields.source_url}
          onChange={(e) => setField("source_url", e.target.value)}
        />
      </div>
      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save metadata"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            reset();
            onCancel();
          }}
        >
          Cancel
        </Button>
        {!saving && (
          <span className="self-center text-xs text-ink-soft">
            {dirty ? "Unsaved changes" : "All fields optional except the name"}
          </span>
        )}
      </div>
    </form>
  );
}

const OVERVIEW_FIELD_LABELS = [
  ["scheme_name", "Name"],
  ["department_name", "Department"],
  ["scheme_category", "Category"],
  ["target_persona", "Target persona"],
  ["status", "Status"],
  ["start_date", "Start date"],
  ["end_date", "End date"],
  ["application_window_type", "Application window"],
  ["official_source_url", "Official source URL"],
  ["application_url", "Application URL"],
  ["official_scheme_identifier", "Official identifier"],
  ["source_type", "Source type"],
  ["source_name", "Source name"],
  ["source_url", "Source URL"],
  ["scheme_version", "Scheme version"],
  ["last_updated_at", "Last updated"],
];

export default function AdminSchemeDetailPage() {
  const { id } = useParams();
  const [scheme, setScheme] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(null); // null | archive | restore | delete
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [tab, setTab] = useState("overview");

  const load = useCallback(() => {
    adminService
      .schemeDetail(id)
      .then((response) => {
        setScheme(response.data);
        setError("");
      })
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load this scheme."))
      );
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const runLifecycle = async () => {
    setBusy(true);
    setActionError("");
    try {
      if (confirming === "archive") await adminService.archiveScheme(id);
      else if (confirming === "restore") await adminService.restoreScheme(id);
      else if (confirming === "delete") await adminService.deleteScheme(id);
      setConfirming(null);
      load();
    } catch (requestError) {
      setActionError(extractApiErrorMessage(requestError, "Action failed."));
      setConfirming(null);
    } finally {
      setBusy(false);
    }
  };

  if (error && !scheme) {
    return (
      <div>
        <Link to="/admin/schemes" className="text-sm text-accent-ink underline">
          ← All schemes
        </Link>
        <ErrorState title="Unable to load scheme" message={error} onRetry={load} />
      </div>
    );
  }
  if (!scheme) {
    return <LoadingState label="Loading scheme..." />;
  }

  const active = scheme.status === "ACTIVE";
  const verifying = scheme.last_verified_at
    ? new Date(String(scheme.last_verified_at).slice(0, 10)).toLocaleDateString()
    : null;

  return (
    <div>
      <div className="mb-4">
        <Link to="/admin/schemes" className="text-sm text-accent-ink underline">
          ← All schemes
        </Link>
      </div>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-[26px]">{scheme.scheme_name}</h1>
            <Badge variant={active ? "ok" : "excl"}>{scheme.status}</Badge>
            {verifying && <Badge variant="neutral">Verified {verifying}</Badge>}
          </div>
          <p className="text-xs text-ink-soft mt-1">
            {scheme.department_name || "No department"} ·{" "}
            {scheme.rule_count ?? 0} rule(s) · {scheme.document_count ?? 0}{" "}
            required document(s) · scheme_version {scheme.scheme_version}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="ghost" onClick={() => setEditing((v) => !v)}>
            {editing ? "Close editor" : "Edit metadata"}
          </Button>
          <Button
            size="sm"
            variant={active ? "secondary" : "primary"}
            onClick={() => setConfirming(active ? "archive" : "restore")}
          >
            {active ? "Archive" : "Restore"}
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => setConfirming("delete")}
          >
            Delete
          </Button>
        </div>
      </div>

      {actionError && (
        <p className="text-sm text-excl-ink mb-4">{actionError}</p>
      )}

      {confirming && (
        <ConfirmDialog
          danger={confirming === "delete" || confirming === "archive"}
          title={
            confirming === "delete"
              ? "Delete this scheme?"
              : confirming === "archive"
                ? "Archive this scheme?"
                : "Restore this scheme?"
          }
          busy={busy}
          onConfirm={runLifecycle}
          onCancel={() => setConfirming(null)}
          body={
            confirming === "delete" ? (
              <>
                <p>
                  <strong>
                    This is a permanent hard delete — there is no undo.
                  </strong>
                </p>
                <p>
                  Rule groups, rules and required-document definitions of{" "}
                  <strong>{scheme.scheme_name}</strong> are removed along with
                  the record. It is refused by the backend when the scheme has
                  assessments, linked source documents, or rule provenance
                  (HTTP 409) — archive instead in that case.
                </p>
              </>
            ) : (
              <>
                <p>
                  {confirming === "archive"
                    ? `${scheme.scheme_name} becomes INACTIVE and disappears from all citizen-facing listings.`
                    : `${scheme.scheme_name} becomes ACTIVE and is visible to citizens again.`}
                </p>
                <p>
                  Reversible. Assessments, source documents and provenance are
                  never touched by archive/restore.
                </p>
              </>
            )
          }
        />
      )}

      {editing && (
        <MetaEditForm
          scheme={scheme}
          onSaved={() => load()}
          onCancel={() => setEditing(false)}
        />
      )}

      <nav aria-label="Scheme sections" className="flex gap-1 flex-wrap border-b border-line mb-5">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            aria-current={tab === key ? "page" : undefined}
            className={`px-3 py-2 text-sm -mb-px border-b-2 transition-colors ${
              tab === key
                ? "border-accent text-ink font-medium"
                : "border-transparent text-ink-soft hover:text-ink"
            }`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <section aria-label="Scheme overview">
          {scheme.description && (
            <Card className="mb-4">
              <h3 className="text-sm font-semibold text-ink mb-1.5">
                Description
              </h3>
              <p className="text-sm text-ink-soft max-w-[80ch]">
                {scheme.description}
              </p>
            </Card>
          )}
          {scheme.benefit_description && (
            <Card className="mb-4">
              <h3 className="text-sm font-semibold text-ink mb-1.5">Benefit</h3>
              <p className="text-sm text-ink-soft max-w-[80ch]">
                {scheme.benefit_description}
              </p>
            </Card>
          )}
          <Card>
            <h3 className="text-sm font-semibold text-ink mb-3">Record</h3>
            <dl className="grid md:grid-cols-2 gap-x-8 gap-y-2 text-sm">
              {OVERVIEW_FIELD_LABELS.map(([key, label]) => (
                <div key={key} className="flex justify-between gap-4 border-b border-line/60 py-1">
                  <dt className="text-ink-soft">{label}</dt>
                  <dd className="text-ink text-right break-all">
                    {scheme[key] === null || scheme[key] === undefined || scheme[key] === ""
                      ? "—"
                      : scheme[key] instanceof Date || key.endsWith("_at") || key.endsWith("date")
                        ? String(scheme[key]).slice(0, 10)
                        : String(scheme[key])}
                  </dd>
                </div>
              ))}
            </dl>
          </Card>
        </section>
      )}

      {tab === "rules" && <RuleManager scheme={scheme} onSchemeChanged={load} />}
      {tab === "documents" && <DocumentManager schemeId={id} />}
      {tab === "sources" && <SourceLinkPanel schemeId={id} />}
      {tab === "verification" && <VerificationPanel scheme={scheme} onVerified={load} />}
    </div>
  );
}
