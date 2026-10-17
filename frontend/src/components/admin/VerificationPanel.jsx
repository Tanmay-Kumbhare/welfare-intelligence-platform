import { useState } from "react";
import Button from "../ui/Button";
import Card from "../ui/Card";
import Input from "../ui/Input";
import Badge from "../ui/Badge";
import ConfirmDialog from "./ConfirmDialog";
import { extractApiErrorMessage } from "../../utils/apiError";
import { adminService } from "../../services/api";
import {
  ELIGIBILITY_RULE_PARAMETERS,
  REQUIRED_DOCUMENT_TYPES,
} from "./rulesVocabulary";

/**
 * Explicit scheme verification — the deliberate counterpart to metadata
 * editing. Saving metadata never verifies anything; only the dedicated
 * backend endpoint POST /admin/schemes/{id}/verify sets the verification
 * date/timestamp, and this panel is the only UI surface for it. The
 * frontend never fabricates a verification date: the displayed state comes
 * from the server response.
 */
export default function VerificationPanel({ scheme, onVerified }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dateInput, setDateInput] = useState("");
  const [confirmedItems, setConfirmedItems] = useState({
    rules: false,
    documents: false,
  });

  const verifiedIso = scheme.last_verified_at
    ? String(scheme.last_verified_at).slice(0, 10)
    : null;
  const verifiedDate = verifiedIso ? new Date(`${verifiedIso}T00:00:00`).toLocaleDateString() : null;

  const today = new Date();
  const inputValid = /^\d{4}-\d{2}-\d{2}$/.test(dateInput);
  // Mirrors (does not replace) the backend's authoritative future-date check:
  // the claimed date must be well-formed and not in the future.
  const currentClaimDate =
    inputValid && new Date(`${dateInput}T00:00:00`) <= today;
  const notFuture = currentClaimDate;

  const verify = async () => {
    setBusy(true);
    setError("");
    try {
      await adminService.verifyScheme(scheme.scheme_id, dateInput);
      setConfirming(false);
      setConfirmedItems({ rules: false, documents: false });
      setDateInput("");
      onVerified();
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Verification could not be recorded."));
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Verification">
      <Card className="mb-4">
        <h2 className="text-lg text-ink mb-2">Verification state</h2>
        {verifiedDate ? (
          <p className="text-sm text-ink flex items-center gap-2">
            <Badge variant="ok">VERIFIED</Badge>
            last verified on {verifiedDate}
          </p>
        ) : (
          <p className="text-sm text-ink flex items-center gap-2">
            <Badge variant="neutral">NOT VERIFIED</Badge>
            no verification has ever been recorded for this scheme
          </p>
        )}
        <p className="text-xs text-ink-soft mt-2 max-w-[75ch]">
          Verification means an admin checked this scheme's rules and required
          documents against the official sources. Ordinary metadata edits
          (saving the description, URLs, status…) never claim verification and
          never touch this state.
        </p>
      </Card>

      <Card>
        <h3 className="text-base text-ink mb-1.5">Verify this scheme</h3>
        <p className="text-xs text-ink-soft mb-4 max-w-[75ch]">
          A deliberate, dated claim — confirm you checked the scheme's
          eligibility rules ({ELIGIBILITY_RULE_PARAMETERS.length} supported
          parameters) and required documents ({REQUIRED_DOCUMENT_TYPES.length}
          known types) against the official sources. The backend refuses
          future dates and never auto-verifies.
        </p>
        {error && <p className="text-sm text-excl-ink mb-3">{error}</p>}

        <div className="flex items-end gap-3 flex-wrap">
          <div className="w-56">
            <Input
              id="verify-date"
              label="Verified on"
              type="date"
              value={dateInput}
              onChange={(e) => setDateInput(e.target.value)}
            />
          </div>
          <Button
            variant="primary"
            disabled={
              !inputValid || !notFuture || !dateInput || busy
            }
            onClick={() => setConfirming(true)}
          >
            Record verification
          </Button>
        </div>
        {dateInput && inputValid && !notFuture && !verifiedIso && (
          <p className="text-sm text-excl-ink mt-2">
            A future date would be a false claim — the backend rejects it.
          </p>
        )}
      </Card>

      {confirming && (
        <ConfirmDialog
          title="Record verification?"
          busy={busy}
          confirmDisabled={!confirmedItems.rules || !confirmedItems.documents}
          onConfirm={verify}
          onCancel={() => setConfirming(false)}
          body={
            <>
              <p>
                This records that the scheme{" "}
                <strong>{scheme.scheme_name}</strong> was checked against
                official sources on <strong>{dateInput}</strong>.
              </p>
              <p>
                Before proceeding, confirm you reviewed the scheme's
                eligibility rules and required documents:
              </p>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={confirmedItems.rules}
                  onChange={(e) =>
                    setConfirmedItems((c) => ({ ...c, rules: e.target.checked }))
                  }
                />
                Eligibility rules are backed by official-text citations or an
                explicit human decision today
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={confirmedItems.documents}
                  onChange={(e) =>
                    setConfirmedItems((c) => ({ ...c, documents: e.target.checked }))
                  }
                />
                Required documents match the official application requirements
              </label>
              <p className="text-xs text-ink-soft">
                This is visible to administrators; it does not change
                eligibility outcomes by itself.
              </p>
            </>
          }
          confirmLabel="Yes, record it"
        />
      )}
    </section>
  );
}
