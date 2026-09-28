import { useCallback, useEffect, useState } from "react";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { api } from "../../services/api";

function RuleList({ schemeId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [linkingRule, setLinkingRule] = useState(null);
  const [sentences, setSentences] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get(`/admin/schemes/${schemeId}/rules-with-provenance`)
      .then((response) => setData(response.data))
      .catch(() => setError("Could not load rules."));
  }, [schemeId]);

  useEffect(() => {
    load();
  }, [load]);

  const openPicker = async (rule) => {
    setLinkingRule(rule);
    setSearchQuery("");
    setSearchResult(null);
    setError("");
    try {
      // The backend picks the latest snapshot document for the scheme.
      const response = await api.get(
        `/admin/provenance/schemes/${schemeId}/latest-document-sentences`
      );
      setSentences(response.data);
      setSearchResult(response.data);
    } catch {
      setError("No fetched snapshot available. Fetch a source first, then link rules.");
    }
  };

  const runSearch = async (q) => {
    if (!sentences) return;
    try {
      const response = await api.get(
        `/admin/provenance/documents/${sentences.source_document_id}/sentences`,
        { params: q ? { query: q } : {} }
      );
      setSearchResult(response.data);
    } catch {
      setError("Sentence search failed.");
    }
  };

  const linkSentence = async (rule, index, text) => {
    setBusy(true);
    setError("");
    try {
      await api.post(
        `/admin/provenance/rules/${rule.rule_id}/link?source_document_id=${sentences.source_document_id}&sentence_index=${index}`,
        {} // SentenceSearchQuery body required by the endpoint contract
      );
      setLinkingRule(null);
      setSentences(null);
      load();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Linking failed.");
    } finally {
      setBusy(false);
    }
  };

  const verifyLink = async (rule, provenanceId) => {
    setBusy(true);
    try {
      await api.post(`/admin/provenance/rules/${rule.rule_id}/links/${provenanceId}/verify`);
      load();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Verify failed.");
    } finally {
      setBusy(false);
    }
  };

  if (error && !data) return <p className="text-sm text-excl-ink mt-2">{error}</p>;
  if (!data) return <p className="text-sm text-ink-soft mt-2">Loading rules…</p>;
  if (data.rules.length === 0) return <p className="text-sm text-ink-soft mt-2">No rules defined.</p>;

  return (
    <div className="mt-3 space-y-2">
      {data.rules.map((rule) => {
        const p = rule.provenance;
        return (
          <div key={rule.rule_id} className="border border-line rounded-sm p-3 bg-paper">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-xs text-ink-soft">
                <span className="text-ink font-mono">{rule.parameter_name}</span>{" "}
                {rule.operator.replace(/_/g, " ").toLowerCase()} {" "}
                <span className="text-ink font-mono">{rule.required_value}</span>
                {rule.rule_description && <span> — {rule.rule_description}</span>}
              </p>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => (linkingRule?.rule_id === rule.rule_id ? (setLinkingRule(null), setSentences(null)) : openPicker(rule))}>
                  {p ? "Re-link source" : "Link source"}
                </Button>
                {p && p.verification_status === "PENDING" && (
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => verifyLink(rule, p.rule_provenance_id)}>
                    Verify citation
                  </Button>
                )}
              </div>
            </div>
            {p ? (
              <div className="mt-2 border-l-2 border-accent pl-3 py-1">
                <p className="text-xs text-ink italic">“{p.source_text}”</p>
                <p className="text-[11px] text-ink-soft mt-1">
                  {p.document_url} · {p.verification_status}
                  {p.verified_at ? ` · verified ${new Date(p.verified_at).toLocaleString()}` : ""}
                </p>
              </div>
            ) : (
              <p className="text-[11px] text-ink-soft mt-1.5 italic">
                No source citation linked yet — this rule is not defensible against the official source.
              </p>
            )}

            {linkingRule?.rule_id === rule.rule_id && sentences && (
              <div className="mt-3 border border-line rounded-sm p-3 bg-white">
                <div className="flex gap-2 mb-2">
                  <input
                    className="flex-1 text-sm px-3 py-2 border border-line rounded-sm"
                    placeholder='Search the snapshot, e.g. "income tax" or "land holding"'
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && runSearch(searchQuery)}
                  />
                  <Button size="sm" onClick={() => runSearch(searchQuery)}>Search</Button>
                </div>
                <p className="text-[11px] text-ink-soft mb-2">
                  {searchResult
                    ? `${searchResult.matches.length} of ${searchResult.total_sentences} sentences${searchQuery && searchResult.query ? ` matching “${searchQuery}”` : ""}`
                    : "Loading sentences…"}
                </p>
                <div className="max-h-56 overflow-auto space-y-1.5">
                  {(searchResult?.matches || []).map((match) => (
                    <button
                      key={match.index}
                      type="button"
                      disabled={busy}
                      className="w-full text-left text-xs p-2 border border-line rounded-sm hover:bg-accent-tint"
                      onClick={() => linkSentence(rule, match.index, match.text)}
                    >
                      <span className="text-ink-soft font-mono mr-2">[{match.index}]</span>
                      {match.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
      {error && <p className="text-xs text-excl-ink">{error}</p>}
      <p className="text-xs text-ink-soft italic">
        Rules are read-only — only their source citations are managed here.
        A citation must be verified by an admin before it is defensible.
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
