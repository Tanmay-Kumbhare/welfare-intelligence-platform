import { useCallback, useEffect, useState } from "react";
import Button from "../ui/Button";
import Card from "../ui/Card";
import Input from "../ui/Input";
import Badge from "../ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "../ui/StatusStates";
import ConfirmDialog from "./ConfirmDialog";
import { extractApiErrorMessage } from "../../utils/apiError";
import { adminService } from "../../services/api";

/**
 * Scheme ↔ source-snapshot association panel over the BACKEND's existing
 * SchemeSourceDocument.scheme_id column (SchemeSourceLinkService). NO source
 * creation workflow lives here — sources/resources/ingestion are managed on
 * the dedicated Sources pages. Snapshots are NEVER deleted from this UI:
 * unlinking only clears the association and the backend preserves the
 * snapshot (its content and citations) untouched.
 */

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function LinkForm({ schemeId, linkedIds, onChanged, onError }) {
  const [sourceDocumentId, setSourceDocumentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      await adminService.linkSchemeSourceDocument(schemeId, sourceDocumentId.trim());
      setSourceDocumentId("");
      onChanged();
    } catch (requestError) {
      setFormError(extractApiErrorMessage(requestError, "Linking failed."));
    } finally {
      setBusy(false);
    }
  };

  const alreadyLinked = linkedIds.has(sourceDocumentId.trim().toLowerCase());

  return (
    <form onSubmit={submit} className="border border-line rounded-sm p-4 bg-paper-raised mb-4">
      <h3 className="text-base text-ink mb-1.5">Link an existing source snapshot</h3>
      <p className="text-xs text-ink-soft mb-3 max-w-[75ch]">
        Paste the snapshot ID shown in a run's detail on the{" "}
        <strong>Sources</strong> page. Only association changes here — content,
        hashes and citations belong to the ingestion workflow. Linking an
        already-linked snapshot is safe (idempotent).
      </p>
      {formError && <p className="text-sm text-excl-ink mb-3">{formError}</p>}
      <div className="flex gap-2 items-start max-w-[560px] flex-wrap">
        <div className="flex-1 min-w-[280px]">
          <Input
            id="link-snapshot-id"
            label="Source snapshot ID"
            placeholder="00000000-0000-0000-0000-000000000000"
            value={sourceDocumentId}
            onChange={(e) => setSourceDocumentId(e.target.value)}
          />
        </div>
        <Button
          type="submit"
          className="mb-5"
          disabled={
            busy ||
            !UUID_PATTERN.test(sourceDocumentId.trim()) ||
            alreadyLinked
          }
        >
          {busy ? "Linking…" : "Link snapshot"}
        </Button>
      </div>
      {alreadyLinked && (
        <p className="text-xs text-ink-soft">This snapshot is already linked below.</p>
      )}
    </form>
  );
}

export default function SourceLinkPanel({ schemeId }) {
  const [documents, setDocuments] = useState(null);
  const [error, setError] = useState("");
  const [bannerError, setBannerError] = useState("");
  const [confirmingUnlink, setConfirmingUnlink] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    adminService
      .listSchemeSourceDocuments(schemeId)
      .then((response) => {
        setDocuments(response.data || []);
        setError("");
      })
      .catch((requestError) =>
        setError(
          extractApiErrorMessage(requestError, "Could not load linked source documents.")
        )
      );
  }, [schemeId]);

  useEffect(() => {
    load();
  }, [load]);

  const unlink = async () => {
    setBusy(true);
    try {
      await adminService.unlinkSchemeSourceDocument(
        schemeId,
        confirmingUnlink.source_document_id
      );
      setConfirmingUnlink(null);
      load();
    } catch (requestError) {
      setBannerError(extractApiErrorMessage(requestError, "Unlinking failed."));
      setConfirmingUnlink(null);
    } finally {
      setBusy(false);
    }
  };

  if (error && documents === null) {
    return <ErrorState title="Unable to load sources" message={error} onRetry={load} />;
  }
  if (documents === null) {
    return <LoadingState label="Loading linked sources..." />;
  }

  const linkedIds = new Set(
    documents.map((document) => document.source_document_id.toLowerCase())
  );

  return (
    <section aria-label="Sources and provenance">
      {bannerError && <p className="text-sm text-excl-ink mb-3">{bannerError}</p>}

      <LinkForm
        schemeId={schemeId}
        linkedIds={linkedIds}
        onChanged={load}
        onError={setBannerError}
      />

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg text-ink">
          Linked source snapshots{" "}
          <Badge pill>{documents.length}</Badge>
        </h2>
      </div>

      {documents.length === 0 ? (
        <EmptyState
          title="Nothing linked yet"
          message="Fetch a source on the Sources pages, then link its snapshot here so rule citations and provenance can be traced."
        />
      ) : (
        <div className="space-y-3">
          {documents.map((document) => (
            <Card key={document.source_document_id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-base text-ink">{document.document_name}</span>
                    <Badge pill>v{document.version}</Badge>
                    <Badge variant="ok">LINKED</Badge>
                  </div>
                  <p className="text-xs text-ink-soft font-mono break-all mt-1">
                    {document.document_url}
                  </p>
                  <p className="text-[11px] text-ink-soft mt-1 break-all">
                    snapshot <span className="font-mono">{document.source_document_id}</span>
                    {document.content_hash
                      ? ` · SHA-256 ${document.content_hash.slice(0, 12)}…`
                      : ""}
                    {document.retrieved_at
                      ? ` · retrieved ${new Date(document.retrieved_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setConfirmingUnlink(document)}
                >
                  Unlink
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {confirmingUnlink && (
        <ConfirmDialog
          danger
          busy={busy}
          title="Unlink this source snapshot?"
          onConfirm={unlink}
          onCancel={() => setConfirmingUnlink(null)}
          body={
            <>
              <p>
                <strong>{confirmingUnlink.document_name}</strong> will no longer
                be associated with this scheme.
              </p>
              <p>
                The snapshot itself is NOT deleted — its content, hash and any
                rule citations are preserved by the backend. Reversal: link the
                snapshot again by its ID at any time.
              </p>
            </>
          }
        />
      )}
    </section>
  );
}
