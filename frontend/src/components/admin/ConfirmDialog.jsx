import { useEffect, useRef } from "react";

/**
 * Modal confirmation dialog for destructive/major actions (delete scheme,
 * archive, restore, verify, rule deletion, document deletion, unlink…).
 *
 * The explanatory body (what WILL happen, what it does NOT do, whether it is
 * reversible) is passed as `body`; the caller owns all semantics. Escape and
 * the overlay click cancel. Focus starts on the Cancel button so Enter
 * confirms nothing accidentally.
 *
 * Absolutely no fake-undo: the caller must describe exactly what the backend
 * will do. If the backend hard-deletes, the body must say that.
 */
export default function ConfirmDialog({
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  confirmDisabled = false,
  onConfirm,
  onCancel,
}) {
  const cancelRef = useRef(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy, onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-5"
      role="presentation"
    >
      <div
        className="absolute inset-0 bg-ink/50"
        onClick={() => !busy && onCancel()}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="relative bg-paper-raised border border-line rounded-sm shadow-lg w-full max-w-md p-5"
      >
        <h2 id="confirm-dialog-title" className="text-lg text-ink mb-2">
          {title}
        </h2>
        <div className="text-sm text-ink-soft space-y-2 mb-5">{body}</div>
        <div className="flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            className="px-4 py-2 text-sm border border-line rounded-sm text-ink hover:border-ink-soft disabled:opacity-50"
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`px-4 py-2 text-sm rounded-sm text-white disabled:opacity-50 ${
              danger
                ? "bg-excl-ink hover:brightness-90"
                : "bg-accent hover:bg-accent-ink"
            }`}
            onClick={onConfirm}
            disabled={busy || confirmDisabled}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
