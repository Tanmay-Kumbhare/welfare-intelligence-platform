/**
 * Turn any axios/API error into a human-readable message.
 *
 * FastAPI returns validation errors (422) as { detail: [ { loc, msg, type } ] }
 * — an array, not a string — and network failures have no response at all.
 * Both used to fall through to a useless generic message on the register form.
 */
export function extractApiErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  const detail = error?.response?.data?.detail;

  // FastAPI validation errors: detail is an array of field errors.
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(" → ") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }

  if (typeof detail === "string" && detail) {
    return detail;
  }

  // No response at all: the backend is unreachable.
  if (error && !error.response) {
    return "Cannot reach the server. Make sure the backend is running on port 8000, then try again.";
  }

  // A response arrived but with no usable detail (proxy 502/504 HTML, bare
  // 500, etc.). Surface the status so the failure can't hide behind a
  // generic message.
  const status = error?.response?.status;
  const rawData = error?.response?.data;
  const bodyHint =
    typeof rawData === "string" && rawData
      ? ` — ${rawData.slice(0, 140)}`
      : "";
  if (status) {
    return `Server error (HTTP ${status})${bodyHint}. If this is 502/504, the backend is not running — start uvicorn and try again.`;
  }

  return fallback;
}
