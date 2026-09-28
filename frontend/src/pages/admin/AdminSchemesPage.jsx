import { useCallback, useEffect, useState } from "react";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { api } from "../../services/api";

function RuleList({ schemeId }) {
  const [rules, setRules] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/schemes/${schemeId}`)
      .then((response) => setRules(response.data.rule_groups || []))
      .catch(() => setError("Could not load rules."));
  }, [schemeId]);

  if (error) return <p className="text-sm text-excl-ink mt-2">{error}</p>;
  if (!rules) return <p className="text-sm text-ink-soft mt-2">Loading rules…</p>;
  if (rules.length === 0) return <p className="text-sm text-ink-soft mt-2">No rules defined.</p>;

  return (
    <div className="mt-3 space-y-3">
      {rules.map((group) => (
        <div key={group.group_id} className="border border-line rounded-sm p-3 bg-paper">
          <p className="text-xs font-medium text-ink mb-1.5">
            {group.group_name}{" "}
            <span className="text-ink-soft font-normal">({group.intra_group_operator} within group)</span>
          </p>
          <ul className="space-y-1">
            {(group.rules || []).map((rule) => (
              <li key={rule.rule_id} className="text-xs text-ink-soft">
                <span className="text-ink font-mono">{rule.parameter_name}</span>{" "}
                {rule.operator.replace(/_/g, " ").toLowerCase()}{" "}
                <span className="text-ink font-mono">{rule.required_value}</span>
                {rule.rule_description && <span> — {rule.rule_description}</span>}
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="text-xs text-ink-soft italic">
        Rules are read-only in this phase — they define eligibility and change
        only through the reviewed ingestion workflow.
      </p>
    </div>
  );
}

function SchemeRow({ scheme, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [showRules, setShowRules] = useState(false);
  const [draft, setDraft] = useState({
    description: scheme.description || "",
    benefit_description: scheme.benefit_description || "",
    official_source_url: scheme.official_source_url || "",
    application_url: scheme.application_url || "",
    status: scheme.status || "ACTIVE",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await api.patch(`/admin/schemes/${scheme.scheme_id}`, draft);
      setEditing(false);
      onSaved();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-lg text-ink">{scheme.scheme_name}</h3>
            <span
              className={`text-xs px-2 py-0.5 rounded-sm ${
                scheme.status === "ACTIVE"
                  ? "bg-ok-tint text-ok-ink"
                  : "bg-excl-tint text-excl-ink"
              }`}
            >
              {scheme.status}
            </span>
          </div>
          <p className="text-xs text-ink-soft mt-1">
            {scheme.department_name || "—"} · {scheme.rule_count ?? "?"} rules
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setShowRules((v) => !v)}>
            {showRules ? "Hide rules" : "View rules"}
          </Button>
          <Button
            size="sm"
            variant={editing ? "secondary" : "primary"}
            onClick={() => (editing ? save() : setEditing(true))}
            disabled={saving}
          >
            {editing ? (saving ? "Saving…" : "Save") : "Edit metadata"}
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-excl-ink mt-3">{error}</p>}

      {editing ? (
        <div className="mt-4 grid md:grid-cols-2 gap-x-5">
          <div className="md:col-span-2">
            <Input
              id={`desc-${scheme.scheme_id}`}
              label="Description"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </div>
          <Input
            id={`benefit-${scheme.scheme_id}`}
            label="Benefit description"
            value={draft.benefit_description}
            onChange={(e) => setDraft({ ...draft, benefit_description: e.target.value })}
          />
          <Input
            id={`source-${scheme.scheme_id}`}
            label="Official source URL"
            value={draft.official_source_url}
            onChange={(e) => setDraft({ ...draft, official_source_url: e.target.value })}
          />
          <Input
            id={`apply-${scheme.scheme_id}`}
            label="Application URL"
            value={draft.application_url}
            onChange={(e) => setDraft({ ...draft, application_url: e.target.value })}
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
            </select>
          </label>
        </div>
      ) : (
        scheme.description && (
          <p className="text-sm text-ink-soft mt-3 max-w-[70ch]">{scheme.description}</p>
        )
      )}

      {showRules && <RuleList schemeId={scheme.scheme_id} />}
    </Card>
  );
}

export default function AdminSchemesPage() {
  const [schemes, setSchemes] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .get("/admin/schemes")
      .then((response) => setSchemes(response.data))
      .catch((requestError) =>
        setError(requestError?.response?.data?.detail || "Could not load schemes.")
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !schemes) {
    return <ErrorState title="Unable to load schemes" message={error} />;
  }
  if (!schemes) {
    return <LoadingState label="Loading schemes..." />;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-[30px] mb-2">Schemes</h1>
        <p className="max-w-[60ch]">
          Metadata is admin-editable. Eligibility rules are visible but
          read-only — they change only through the reviewed ingestion
          workflow, never by direct edits.
        </p>
      </div>
      <div className="space-y-4">
        {schemes.map((scheme) => (
          <SchemeRow key={scheme.scheme_id} scheme={scheme} onSaved={load} />
        ))}
      </div>
    </div>
  );
}
