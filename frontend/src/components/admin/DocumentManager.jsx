import { useCallback, useEffect, useState } from "react";
import Button from "../ui/Button";
import Card from "../ui/Card";
import Input from "../ui/Input";
import Select from "../ui/Select";
import Badge from "../ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "../ui/StatusStates";
import ConfirmDialog from "./ConfirmDialog";
import { extractApiErrorMessage } from "../../utils/apiError";
import { adminService } from "../../services/api";
import { REQUIRED_DOCUMENT_TYPES } from "./rulesVocabulary";

/**
 * Required-documents admin over the backend DocumentAdminService endpoints.
 *
 * USES ONLY the existing document-type vocabulary (the same types the
 * citizen flows validate). The schema has no active/deactivated column, so
 * deletion REMOVES the requirement permanently — the dialog states exactly
 * that instead of implying a deactivate/archive that does not exist.
 */

function DocumentEditor({ schemeId, existingDocument, onError, onDone }) {
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [fields, setFields] = useState({
    document_type: existingDocument?.document_type || "",
    mandatory_flag: existingDocument ? String(existingDocument.mandatory_flag) : "true",
    description: existingDocument?.description || "",
  });
  const setField = (name, value) =>
    setFields((current) => ({ ...current, [name]: value }));

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const payload = {
      document_type: fields.document_type,
      mandatory_flag: fields.mandatory_flag === "true",
      description: fields.description || null,
    };
    try {
      if (existingDocument) {
        await adminService.updateDocument(
          schemeId,
          existingDocument.document_id,
          payload
        );
      } else {
        await adminService.createDocument(schemeId, payload);
      }
      onDone();
    } catch (requestError) {
      setFormError(
        extractApiErrorMessage(requestError, "The server rejected this requirement.")
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="border border-line rounded-sm p-4 bg-white mt-2">
      {formError && <p className="text-sm text-excl-ink mb-3">{formError}</p>}
      <div className="grid md:grid-cols-3 gap-x-5">
        <Select
          id={`doc-type-${existingDocument?.document_id ?? "new"}`}
          label="Document type"
          required
          hint="Only the types the platform already uses — no new categories"
          value={fields.document_type}
          onChange={(e) => setField("document_type", e.target.value)}
        >
          <option value="">— select type —</option>
          {REQUIRED_DOCUMENT_TYPES.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </Select>
        <Select
          id={`doc-mandatory-${existingDocument?.document_id ?? "new"}`}
          label="Requirement mode"
          required
          hint="Mandatory: missing/invalid blocks the recommendation. Optional: never blocks."
          value={fields.mandatory_flag}
          onChange={(e) => setField("mandatory_flag", e.target.value)}
        >
          <option value="true">Mandatory</option>
          <option value="false">Optional</option>
        </Select>
        <Input
          id={`doc-desc-${existingDocument?.document_id ?? "new"}`}
          label="Description (optional)"
          hint="What exactly the citizen should hold ready"
          value={fields.description}
          onChange={(e) => setField("description", e.target.value)}
        />
      </div>
      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving || !fields.document_type}>
          {saving ? "Saving…" : existingDocument ? "Save requirement" : "Add requirement"}
        </Button>
        <Button type="button" variant="secondary" onClick={onDone} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DocumentRow({ schemeId, documentId, document, onChanged, onError }) {
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const deleteDocument = async () => {
    setBusy(true);
    try {
      await adminService.deleteDocument(schemeId, documentId);
      setConfirmingDelete(false);
      onChanged();
    } catch (requestError) {
      onError(extractApiErrorMessage(requestError, "Deletion failed."));
      setConfirmingDelete(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base text-ink">{document.document_type}</h3>
            <Badge variant={document.mandatory_flag ? "excl" : "neutral"}>
              {document.mandatory_flag ? "MANDATORY" : "OPTIONAL"}
            </Badge>
          </div>
          {document.description && (
            <p className="text-xs text-ink-soft mt-1 max-w-[70ch]">
              {document.description}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setEditing((v) => !v)}>
            {editing ? "Close editor" : "Edit"}
          </Button>
          <Button size="sm" variant="danger" onClick={() => setConfirmingDelete(true)}>
            Remove
          </Button>
        </div>
      </div>

      {editing && (
        <DocumentEditor
          schemeId={schemeId}
          existingDocument={document}
          onError={onError}
          onDone={() => {
            setEditing(false);
            onChanged();
          }}
        />
      )}

      {confirmingDelete && (
        <ConfirmDialog
          danger
          busy={busy}
          title={`Remove the ${document.document_type} requirement?`}
          onConfirm={deleteDocument}
          onCancel={() => setConfirmingDelete(false)}
          body={
            <>
              <p>
                This permanently removes the requirement from the citizen
                checklist for this scheme.
              </p>
              <p>
                The schema has no “deactivated” state, so removal is a real
                delete — past assessments keep their own snapshots and are
                unaffected, but there is no undo for the requirement itself.
              </p>
            </>
          }
        />
      )}
    </Card>
  );
}

export default function DocumentManager({ schemeId }) {
  const [documents, setDocuments] = useState(null);
  const [error, setError] = useState("");
  const [bannerError, setBannerError] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    adminService
      .listDocuments(schemeId)
      .then((response) => {
        setDocuments(response.data || []);
        setError("");
      })
      .catch((requestError) =>
        setError(extractApiErrorMessage(requestError, "Could not load required documents."))
      );
  }, [schemeId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error && documents === null) {
    return <ErrorState title="Unable to load documents" message={error} onRetry={load} />;
  }
  if (documents === null) {
    return <LoadingState label="Loading required documents..." />;
  }

  return (
    <section aria-label="Required documents">
      {bannerError && <p className="text-sm text-excl-ink mb-3">{bannerError}</p>}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg text-ink">Required documents</h2>
          <p className="text-xs text-ink-soft max-w-[70ch] mt-0.5">
            The checklist citizens are asked for. Mandatory documents
            missing/invalid block a citizen's recommendation; optional ones
            never do.
          </p>
        </div>
        <Button
          size="sm"
          variant="primary"
          onClick={() => setCreating((v) => !v)}
        >
          {creating ? "Close" : "+ Add requirement"}
        </Button>
      </div>

      {creating && (
        <DocumentEditor
          schemeId={schemeId}
          onError={setBannerError}
          onDone={() => {
            setCreating(false);
            load();
          }}
        />
      )}

      <div className="mt-3 space-y-3">
        {documents.length === 0 ? (
          <EmptyState
            title="No required documents"
            message="Add the documents the authority demands at application time."
            action={
              !creating && (
                <Button variant="secondary" onClick={() => setCreating(true)}>
                  + Add requirement
                </Button>
              )
            }
          />
        ) : (
          documents.map((document) => (
            <DocumentRow
              key={document.document_id}
              schemeId={schemeId}
              document={document}
              documentId={document.document_id}
              onChanged={load}
              onError={setBannerError}
            />
          ))
        )}
      </div>
    </section>
  );
}
