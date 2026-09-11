// The backend has no authentication/session layer yet — a citizen record
// is just a row created via POST /citizens/. To let "My Profile" and
// "Re-check eligibility" work across page reloads without inventing a
// fake backend feature, we keep a pointer to the citizen the person most
// recently created, in this browser only. This is a frontend convenience,
// not persisted server-side, and holds no personal data itself — only
// the UUID.

const STORAGE_KEY = "vidyasetu.citizen_id";

export function getStoredCitizenId() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredCitizenId(citizenId) {
  try {
    window.localStorage.setItem(STORAGE_KEY, citizenId);
  } catch {
    // Ignore storage failures (e.g. private browsing) — the app still
    // works within the current session via in-memory navigation state.
  }
}

export function clearStoredCitizenId() {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // no-op
  }
}
