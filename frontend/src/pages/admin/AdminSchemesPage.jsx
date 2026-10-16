import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import Select from "../../components/ui/Select";
import Badge from "../../components/ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StatusStates";
import ConfirmDialog from "../../components/admin/ConfirmDialog";
import useAdminDraft from "../../components/admin/useAdminDraft";
import { extractApiErrorMessage } from "../../utils/apiError";
import { adminService } from "../../services/api";
import {
  APPLICATION_WINDOW_TYPES,
  GROUP_OPERATORS,
  SCHEME_CATEGORIES,
  SCHEME_PERSONAS,
  SCHEME_SOURCE_TYPES,
  SCHEME_STATUSES,
} from "../../components/admin/rulesVocabulary";

const STATUS_BADGE_VARIANT = { ACTIVE: "ok", INACTIVE: "excl" };

/** ISO date (YYYY-MM-DD) or "" — client-side affordance only. */
function isValidIsoDate(value) {
  if (!value) return true;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  return !Number.isNaN(new Date(`${value}T00:00:00`).getTime());
}

export function CreateSchemeForm({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const { fields, setField, dirty, reset } = useAdminDraft({
    scheme_name: "",
    department_name: "",
    scheme_category: "EDUCATION",
    target_persona: "STUDENT",
    description: "",
    benefit_description: "",
    start_date: "",
    end_date: "",
    status: "ACTIVE",
    official_source_url: "",
    application_url: "",
    official_scheme_identifier: "",
    source_type: "MANUAL_SEED",
    source_name: "",
    application_window_type: "",
    source_url: "",
    group_combining_operator: "AND",
  });

  const fieldErrors = {};
  if (!fields.scheme_name.trim()) {
    fieldErrors.scheme_name = "Scheme name is required";
  } else if (fields.scheme_name.length > 255) {
    fieldErrors.scheme_name = "Must be at most 255 characters";
  }
  if (!isValidIsoDate(fields.start_date)) {
    fieldErrors.start_date = "Use YYYY-MM-DD";
  }
  if (!isValidIsoDate(fields.end_date)) {
    fieldErrors.end_date = "Use YYYY-MM-DD";
  }
  if (
    isValidIsoDate(fields.start_date) &&
    isValidIsoDate(fields.end_date) &&
    fields.start_date &&
    fields.end_date &&
    fields.end_date < fields.start_date
  ) {
    fieldErrors.end_date = "End date must not be before the start date";
  }

  const canSubmit =
    !saving &&
    fields.scheme_name.trim() &&
    Object.keys(fieldErrors).length === 0;

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        + Create scheme
      </Button>
    );
  }

  const create = async () => {
    setSaving(true);
    setError("");
    try {
      // Send only non-empty optional strings; empty date strings must not
      // become ISO-date validation errors on the server.
      const payload = {};
      for (const [key, value] of Object.entries(fields)) {
        if (value !== "") payload[key] = value;
      }
      const response = await adminService.createScheme(payload);
      setOpen(false);
      onCreated(response.data);
      // Fresh empty draft for the next creation (never leaks the old values).
      reset();
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Could not create scheme."));
    } finally {
      setSaving(false);
    }
  };

  const cancel = () => {
    if (dirty && !window.confirm("Discard unsaved scheme details?")) return;
    setOpen(false);
    reset();
    setError("");
  };

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 className="text-lg text-ink">Create a scheme</h3>
        <Button variant="ghost" size="sm" onClick={cancel}>
          Close
        </Button>
      </div>
      <p className="text-xs text-ink-soft mb-4 max-w-[70ch]">
        Creates curated scheme metadata only — no eligibility rules and no
        required documents yet. An active scheme with zero rules is evaluated
        as not eligible for citizens until rules are added in the scheme's
        detail view. Nothing here claims the scheme was verified against
        official sources — that is a separate deliberate action.
      </p>
      {error && <p className="text-sm text-excl-ink mb-3">{error}</p>}
      <div className="grid md:grid-cols-2 gap-x-5">
        <Input
          id="new-scheme-name"
          label="Scheme name"
          required
          value={fields.scheme_name}
          error={fieldErrors.scheme_name}
          onChange={(e) => setField("scheme_name", e.target.value)}
        />
        <Input
          id="new-scheme-department"
          label="Department"
          value={fields.department_name}
          onChange={(e) => setField("department_name", e.target.value)}
        />
        <Select
          id="new-scheme-category"
          label="Category"
          value={fields.scheme_category}
          onChange={(e) => setField("scheme_category", e.target.value)}
        >
          {SCHEME_CATEGORIES.map((category) => (
            <option key={category} value={category}>{category}</option>
          ))}
        </Select>
        <Select
          id="new-scheme-persona"
          label="Target persona"
          value={fields.target_persona}
          onChange={(e) => setField("target_persona", e.target.value)}
        >
          {SCHEME_PERSONAS.map((persona) => (
            <option key={persona} value={persona}>{persona}</option>
          ))}
        </Select>
        <div className="md:col-span-2">
          <Input
            id="new-scheme-description"
            label="Description"
            value={fields.description}
            onChange={(e) => setField("description", e.target.value)}
          />
        </div>
        <div className="md:col-span-2">
          <Input
            id="new-scheme-benefit"
            label="Benefit description"
            value={fields.benefit_description}
            onChange={(e) => setField("benefit_description", e.target.value)}
          />
        </div>
        <Input
          id="new-scheme-start"
          label="Start date"
          type="date"
          hint="ISO date — leave empty when unknown"
          value={fields.start_date}
          error={fieldErrors.start_date}
          onChange={(e) => setField("start_date", e.target.value)}
        />
        <Input
          id="new-scheme-end"
          label="End date"
          type="date"
          value={fields.end_date}
          error={fieldErrors.end_date}
          onChange={(e) => setField("end_date", e.target.value)}
        />
        <Select
          id="new-scheme-status"
          label="Status"
          value={fields.status}
          onChange={(e) => setField("status", e.target.value)}
        >
          {SCHEME_STATUSES.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </Select>
        <Select
          id="new-scheme-window"
          label="Application window type"
          hint="Leave empty when unknown"
          value={fields.application_window_type}
          onChange={(e) => setField("application_window_type", e.target.value)}
        >
          <option value="">— not specified —</option>
          {APPLICATION_WINDOW_TYPES.map((windowType) => (
            <option key={windowType} value={windowType}>{windowType}</option>
          ))}
        </Select>
        <Input
          id="new-scheme-official-url"
          label="Official source URL"
          type="url"
          hint="https://…"
          value={fields.official_source_url}
          onChange={(e) => setField("official_source_url", e.target.value)}
        />
        <Input
          id="new-scheme-apply-url"
          label="Application URL"
          type="url"
          hint="https://…"
          value={fields.application_url}
          onChange={(e) => setField("application_url", e.target.value)}
        />
        <Select
          id="new-scheme-source-type"
          label="Source type (provenance)"
          hint="MANUAL_SEED is the honest default for hand-curated records"
          value={fields.source_type}
          onChange={(e) => setField("source_type", e.target.value)}
        >
          {SCHEME_SOURCE_TYPES.map((sourceType) => (
            <option key={sourceType} value={sourceType}>{sourceType}</option>
          ))}
        </Select>
        <Input
          id="new-scheme-source-name"
          label="Source name"
          value={fields.source_name}
          onChange={(e) => setField("source_name", e.target.value)}
        />
        <Input
          id="new-scheme-source-url"
          label="Source URL"
          type="url"
          value={fields.source_url}
          onChange={(e) => setField("source_url", e.target.value)}
        />
        <Input
          id="new-scheme-identifier"
          label="Official scheme identifier"
          hint="As named by the authority, when known"
          value={fields.official_scheme_identifier}
          onChange={(e) => setField("official_scheme_identifier", e.target.value)}
        />
        <Select
          id="new-scheme-combining"
          label="Group combining operator"
          hint="How the scheme's eligibility groups combine (eligible if AND: all groups pass / OR: any group passes)"
          value={fields.group_combining_operator}
          onChange={(e) => setField("group_combining_operator", e.target.value)}
        >
          {GROUP_OPERATORS.map((operator) => (
            <option key={operator} value={operator}>{operator}</option>
          ))}
        </Select>
      </div>
      <div className="flex gap-2 mt-4">
        <Button onClick={create} disabled={!canSubmit}>
          {saving ? "Creating…" : "Create scheme"}
        </Button>
        <Button variant="secondary" onClick={cancel}>
          Cancel
        </Button>
      </div>
    </Card>
  );
}

export function SchemeRow({ scheme, onChanged, onError }) {
  const [confirming, setConfirming] = useState(null); // null | "archive" | "restore"
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState("");

  const runToggle = async () => {
    setBusy(true);
    setRowError("");
    try {
      if (confirming === "archive") {
        await adminService.archiveScheme(scheme.scheme_id);
      } else {
        await adminService.restoreScheme(scheme.scheme_id);
      }
      setConfirming(null);
      onChanged();
    } catch (requestError) {
      const message = extractApiErrorMessage(requestError, "Action failed.");
      setRowError(message);
      onError?.(message);
      setConfirming(null);
    } finally {
      setBusy(false);
    }
  };

  const active = scheme.status === "ACTIVE";

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/admin/schemes/${scheme.scheme_id}`}
              className="text-lg text-accent-ink hover:underline"
            >
              {scheme.scheme_name}
            </Link>
            <Badge variant={STATUS_BADGE_VARIANT[scheme.status] || "neutral"}>
              {scheme.status}
            </Badge>
            {scheme.scheme_category && (
              <Badge pill>{scheme.scheme_category}</Badge>
            )}
            {scheme.target_persona && <Badge pill>{scheme.target_persona}</Badge>}
          </div>
          <p className="text-xs text-ink-soft mt-1">
            {scheme.department_name || "No department recorded"} ·{" "}
            {scheme.rule_count ?? 0} rule{(scheme.rule_count ?? 0) === 1 ? "" : "s"} ·{" "}
            {(scheme.rule_count ?? 0) === 0 && active ? (
              <span className="text-accent-ink">no eligibility rules yet</span>
            ) : null}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" to={`/admin/schemes/${scheme.scheme_id}`}>
            Open detail
          </Button>
          <Button
            size="sm"
            variant={active ? "secondary" : "primary"}
            onClick={() => setConfirming(active ? "archive" : "restore")}
          >
            {active ? "Archive" : "Restore"}
          </Button>
        </div>
      </div>

      {rowError && <p className="text-sm text-excl-ink mt-3">{rowError}</p>}

      {confirming && (
        <ConfirmDialog
          danger={confirming === "archive"}
          title={confirming === "archive" ? "Archive this scheme?" : "Restore this scheme?"}
          busy={busy}
          onConfirm={runToggle}
          onCancel={() => setConfirming(null)}
          body={
            <>
              <p>
                {confirming === "archive" ? (
                  <>
                    <strong>{scheme.scheme_name}</strong> becomes INACTIVE and
                    disappears from all citizen-facing listings.
                  </>
                ) : (
                  <>
                    <strong>{scheme.scheme_name}</strong> becomes ACTIVE and is
                    visible to citizens again.
                  </>
                )}
              </p>
              <p>
                Reversible. Assessments, source documents and provenance are
                never touched by archive/restore.
              </p>
            </>
          }
        />
      )}
    </Card>
  );
}

export default function AdminSchemesPage() {
  const [schemes, setSchemes] = useState(null);
  const [error, setError] = useState("");
  const [bannerError, setBannerError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");

  const load = useCallback(() => {
    adminService
      .listSchemes()
      .then((response) => setSchemes(response.data))
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load schemes."))
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // The list API returns the full catalogue without server-side filters, so
  // search/filter are local projections — not invented backend behaviour.
  const visible = (schemes || []).filter((scheme) => {
    if (statusFilter !== "ALL" && scheme.status !== statusFilter) return false;
    if (!search.trim()) return true;
    const haystack = [
      scheme.scheme_name,
      scheme.department_name,
      scheme.scheme_category,
      scheme.benefit_description,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(search.trim().toLowerCase());
  });

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[30px] mb-2">Schemes</h1>
          <p className="max-w-[60ch]">
            Full catalogue — active and archived. Metadata editing, rules,
            required documents, sources and verification live in each scheme's
            detail view.
          </p>
        </div>
        <CreateSchemeForm
          onCreated={(created) => {
            setActionNotice(
              `Scheme “${created.scheme_name}” created — open it to add rules and required documents.`
            );
            load();
          }}
        />
      </div>

      {actionNotice && (
        <div className="mb-4 border border-ok-tint bg-ok-tint/40 text-ok-ink text-sm rounded-sm p-3 flex justify-between gap-3">
          <span>{actionNotice}</span>
          <button
            type="button"
            className="text-xs underline"
            onClick={() => setActionNotice("")}
          >
            Dismiss
          </button>
        </div>
      )}
      {bannerError && <p className="text-sm text-excl-ink mb-4">{bannerError}</p>}

      <div className="flex gap-3 items-end mb-5 flex-wrap">
        <div className="w-full md:w-72">
          <Input
            id="scheme-search"
            label="Search"
            placeholder="Name, department, category…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          id="scheme-status-filter"
          label="Status"
          className="w-44"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="ALL">ALL</option>
          {SCHEME_STATUSES.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </Select>
        {schemes && (
          <p className="text-xs text-ink-soft pb-6">
            {visible.length} of {schemes.length} scheme
            {schemes.length === 1 ? "" : "s"} shown
          </p>
        )}
      </div>

      {error && !schemes ? (
        <ErrorState title="Unable to load schemes" message={error} onRetry={load} />
      ) : !schemes ? (
        <LoadingState label="Loading schemes..." />
      ) : visible.length === 0 ? (
        <EmptyState
          title={schemes.length === 0 ? "No schemes yet" : "No schemes match"}
          message={
            schemes.length === 0
              ? "Create the first scheme above."
              : "Adjust the search or status filter."
          }
        />
      ) : (
        <div className="space-y-4">
          {visible.map((scheme) => (
            <SchemeRow
              key={scheme.scheme_id}
              scheme={scheme}
              onChanged={load}
              onError={setBannerError}
            />
          ))}
        </div>
      )}
    </div>
  );
}
