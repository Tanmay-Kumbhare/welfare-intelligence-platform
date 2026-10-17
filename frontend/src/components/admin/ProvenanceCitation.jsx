import { useState } from "react";
import Button from "../ui/Button";
import { adminService } from "../../services/api";
import { extractApiErrorMessage } from "../../utils/apiError";

/**
 * Per-rule source citation (provenance) controls. Extracted from the
 * previously working citation UI in the old scheme list page, unchanged in
 * behavior: pick the scheme's latest snapshot document, search its
 * deterministic sentences, link one as the rule's source, verify it.
 *
 * The picker reads whatever snapshot is linked to the scheme (or the newest
 * ACTIVE one); fetches are managed on the Sources pages, never here.
 */
export default function ProvenanceCitation({ rule, provenance, onChanged, onError }) {
  const [open, setOpen] = useState(false);
  const [documentSentences, setDocumentSentences] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");

  const openPicker = async () => {
    setOpen(true);
    setSearchQuery("");
    setSearchResult(null);
    setLocalError("");
    try {
      // The backend picks the latest snapshot document for the scheme.
      const response = await adminService.latestDocumentSentences(rule.scheme_id);
      setDocumentSentences(response.data);
      setSearchResult(response.data);
    } catch {
      setLocalError(
        "No fetched snapshot available. Fetch a source first on the Sources pages, then link rules."
      );
    }
  };

  const runSearch = async (query) => {
    if (!documentSentences) return;
    try {
      const response = await adminService.documentSentences(
        documentSentences.source_document_id,
        query
      );
      setSearchResult(response.data);
    } catch {
      onError("Sentence search failed.");
    }
  };

  const linkSentence = async (sentenceIndex) => {
    setBusy(true);
    setLocalError("");
    try {
      await adminService.linkRuleProvenance(
        rule.rule_id,
        documentSentences.source_document_id,
        sentenceIndex
      );
      setOpen(false);
      setDocumentSentences(null);
      onChanged();
    } catch (requestError) {
      setLocalError(extractApiErrorMessage(requestError, "Linking failed."));
    } finally {
      setBusy(false);
    }
  };

  const verifyLink = async () => {
    setBusy(true);
    setLocalError("");
    try {
      await adminService.verifyRuleProvenance(
        rule.rule_id,
        provenance.rule_provenance_id
      );
      onChanged();
    } catch (requestError) {
      setLocalError(extractApiErrorMessage(requestError, "Verify failed."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2">
      {provenance ? (
        <div className="border-l-2 border-accent pl-3 py-1">
          <p className="text-xs text-ink italic">“{provenance.source_text}”</p>
          <p className="text-[11px] text-ink-soft mt-1">
            {provenance.document_url} · {provenance.verification_status}
            {provenance.verified_at
              ? ` · verified ${new Date(provenance.verified_at).toLocaleString()}`
              : ""}
          </p>
        </div>
      ) : (
        <p className="text-[11px] text-ink-soft mt-1 italic">
          No source citation linked yet — this rule is not defensible against
          the official source.
        </p>
      )}

      <div className="flex gap-2 mt-1.5">
        <Button size="sm" variant="ghost" onClick={() => (open ? setOpen(false) : openPicker())}>
          {provenance ? (open ? "Close picker" : "Re-link source") : "Link source"}
        </Button>
        {provenance && provenance.verification_status === "PENDING" && (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={verifyLink}
          >
            Verify citation
          </Button>
        )}
      </div>

      {localError && <p className="text-[11px] text-excl-ink mt-1">{localError}</p>}

      {open && documentSentences && (
        <div className="mt-2 border border-line rounded-sm p-3 bg-white">
          <div className="flex gap-2 mb-2">
            <input
              className="flex-1 text-sm px-3 py-2 border border-line rounded-sm"
              placeholder='Search the snapshot, e.g. "income tax" or "land holding"'
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch(searchQuery)}
            />
            <Button size="sm" onClick={() => runSearch(searchQuery)}>
              Search
            </Button>
          </div>
          <p className="text-[11px] text-ink-soft mb-2">
            {searchResult
              ? `${searchResult.matches.length} of ${searchResult.total_sentences} sentences${
                  searchQuery && (searchResult.query || searchQuery)
                    ? ` matching “${searchQuery}”`
                    : ""
                }`
              : "Loading sentences…"}
          </p>
          <div className="max-h-56 overflow-auto space-y-1.5">
            {(searchResult?.matches || []).map((match) => (
              <button
                key={match.index}
                type="button"
                disabled={busy}
                className="w-full text-left text-xs p-2 border border-line rounded-sm hover:bg-accent-tint"
                onClick={() => linkSentence(match.index)}
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
}
