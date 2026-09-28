// Lightweight auth store for the token-based frontend approach.
// This keeps auth state in memory + localStorage so the app can survive a
// refresh during development. In a later phase this should become a real
// session/token store with refresh and logout behavior.

const TOKEN_KEY = "vidyasetu.auth_token";
const USER_KEY = "vidyasetu.auth_user";

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // ignore storage failures in private browsing etc.
  }
}

export function clearToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // no-op
  }
}

export function getUser() {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function saveUser(user) {
  try {
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // ignore
  }
}

export function clearUser() {
  try {
    window.localStorage.removeItem(USER_KEY);
  } catch {
    // no-op
  }
}

export function clearAuth() {
  clearToken();
  clearUser();
}

// Attach the current token to outbound auth requests. Other services remain
// public (schemes, form catalogue) unless they are explicitly user-scoped.
export function attachAuthHeaders(config) {
  const token = getToken();
  if (!token) return config;
  const headers = config.headers || {};
  headers["Authorization"] = `Bearer ${token}`;
  return { ...config, headers };
}
