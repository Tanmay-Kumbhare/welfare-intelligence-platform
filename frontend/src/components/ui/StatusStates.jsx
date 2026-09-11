import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import Button from "./Button";

export function LoadingState({ label = "Loading..." }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-ink-soft">
      <Loader2 className="h-5 w-5 animate-spin text-accent" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message = "We couldn't reach the server. Please check your connection and try again.",
  onRetry,
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center px-4 border border-line bg-paper-raised">
      <AlertTriangle className="h-7 w-7 text-excl" />
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      <p className="max-w-md text-sm text-ink-soft">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title = "Nothing here yet", message = "", action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center px-4 border border-line bg-paper-raised">
      <Inbox className="h-6 w-6 text-ink-soft" />
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {message && <p className="max-w-md text-sm text-ink-soft">{message}</p>}
      {action}
    </div>
  );
}
