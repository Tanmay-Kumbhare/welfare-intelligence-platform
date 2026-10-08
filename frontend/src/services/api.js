import axios from "axios";

import { attachAuthHeaders, getToken } from "./auth";

const API_URL = import.meta.env.VITE_API_URL || "/api/v1";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Auto-attach auth headers to any request that goes through the main api client.
api.interceptors.request.use(attachAuthHeaders);

// Auth-specific client keeps its own interceptors separate so login/register
// requests never get polluted by a stale token.
export const authApi = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// ---------------------------------------------------------------------------
// Client-Side TTL Cache & In-Flight Request Deduplication
// ---------------------------------------------------------------------------

const clientCache = new Map();
const inFlightRequests = new Map();

// TTL configurations in milliseconds
const CACHE_RULES = [
  { pattern: /^\/schemes/, ttl: 300_000 },       // 5 minutes
  { pattern: /^\/forms\/[^/]+$/, ttl: 300_000 },  // 5 minutes for form definitions
  { pattern: /^\/auth\/me$/, ttl: 30_000 },       // 30 seconds for current user
  { pattern: /^\/citizens\/[^/]+$/, ttl: 60_000 },// 1 minute for citizen profile
];

function getCacheTTL(url) {
  const matched = CACHE_RULES.find((rule) => rule.pattern.test(url));
  return matched ? matched.ttl : 0;
}

export function invalidateClientCache(urlPattern = null) {
  if (!urlPattern) {
    clientCache.clear();
    return;
  }
  for (const key of clientCache.keys()) {
    if (typeof urlPattern === "string" && key.includes(urlPattern)) {
      clientCache.delete(key);
    } else if (urlPattern instanceof RegExp && urlPattern.test(key)) {
      clientCache.delete(key);
    }
  }
}

// Clear client cache on authentication change
if (typeof window !== "undefined") {
  window.addEventListener("auth-change", () => {
    clientCache.clear();
    inFlightRequests.clear();
  });
}

/**
 * Deduplicated, cached GET request helper for axios.
 */
async function cachedGet(client, url, config = {}) {
  const token = getToken() || "anon";
  const paramsKey = config.params ? JSON.stringify(config.params) : "";
  const cacheKey = `${token}:${url}:${paramsKey}`;
  const now = Date.now();

  // 1. Check client memory cache
  const cached = clientCache.get(cacheKey);
  if (cached && now < cached.expiresAt) {
    return Promise.resolve({ data: cached.data, status: 200, statusText: "OK", headers: {}, config });
  }

  // 2. In-flight request deduplication
  if (inFlightRequests.has(cacheKey)) {
    return inFlightRequests.get(cacheKey);
  }

  // 3. Dispatch fresh network request
  const requestPromise = client.get(url, config)
    .then((response) => {
      const ttl = getCacheTTL(url);
      if (ttl > 0 && response.status === 200) {
        clientCache.set(cacheKey, {
          data: response.data,
          expiresAt: Date.now() + ttl,
        });
      }
      return response;
    })
    .finally(() => {
      inFlightRequests.delete(cacheKey);
    });

  inFlightRequests.set(cacheKey, requestPromise);
  return requestPromise;
}

// ---------------------------------------------------------------------------
// Service Definitions
// ---------------------------------------------------------------------------

export const citizenService = {
  register: async (data) => {
    const res = await api.post("/citizens/", data);
    invalidateClientCache("/citizens");
    invalidateClientCache("/auth/me");
    return res;
  },
  get: (id) => cachedGet(api, `/citizens/${id}`),
  update: async (id, data) => {
    const res = await api.put(`/citizens/${id}`, data);
    invalidateClientCache(`/citizens/${id}`);
    invalidateClientCache("/auth/me");
    return res;
  },
  audit: (citizenId) => {
    if (!citizenId) {
      return Promise.reject(new Error("Citizen ID is required for profile audit"));
    }
    return api.get(`/citizens/audit/${citizenId}`);
  },
  getEducation: (citizenId) => api.get(`/citizens/${citizenId}/education`),
  addEducation: async (citizenId, data) => {
    const res = await api.post(`/citizens/${citizenId}/education`, data);
    invalidateClientCache(`/citizens/${citizenId}`);
    return res;
  },
  updateEducation: async (citizenId, recordId, data) => {
    const res = await api.put(`/citizens/${citizenId}/education/${recordId}`, data);
    invalidateClientCache(`/citizens/${citizenId}`);
    return res;
  },
  deleteEducation: async (citizenId, recordId) => {
    const res = await api.delete(`/citizens/${citizenId}/education/${recordId}`);
    invalidateClientCache(`/citizens/${citizenId}`);
    return res;
  },
};

export const adminService = {
  updateFormQuestion: async (questionId, data) => {
    const res = await api.patch(`/admin/forms/questions/${questionId}`, data);
    invalidateClientCache("/forms");
    return res;
  },
};

export const authService = {
  register: (data) => authApi.post("/auth/register", data),
  login: (data) => authApi.post("/auth/login", data),
  getGoogleAuthUrl: (redirectPath = "/") =>
    authApi.get("/auth/google/url", { params: { redirect_path: redirectPath } }),
  googleCallback: (data) => authApi.post("/auth/google/callback", data),
  getDigiLockerAuthUrl: (redirectPath = "/") =>
    authApi.get("/auth/digilocker/url", { params: { redirect_path: redirectPath } }),
  digilockerCallback: (data) => authApi.post("/auth/digilocker/callback", data),
  me: () => cachedGet(api, "/auth/me"),
  logout: async () => {
    try {
      return await api.post("/auth/logout");
    } finally {
      invalidateClientCache();
    }
  },
};

export const schemeService = {
  getAll: () => cachedGet(api, "/schemes/"),
  get: (id) => cachedGet(api, `/schemes/${id}`),
};

export const eligibilityService = {
  evaluate: (citizenId) => api.post(`/eligibility/evaluate/${citizenId}`),
  simulate: (citizenId, payload) => {
    if (!citizenId) {
      return Promise.reject(new Error("Citizen ID is required for simulation"));
    }
    return api.post(`/eligibility/simulate/${citizenId}`, payload);
  },
};

export const recommendationService = {
  getForCitizen: (citizenId) => api.get(`/recommendations/${citizenId}`),
};

// Phase 2C: database-driven dynamic form
export const formService = {
  getActive: (formCode) => cachedGet(api, `/forms/${formCode}`),
  getPrefill: (formCode) => api.get(`/forms/${formCode}/prefill`),
  getSavedAnswers: (formCode) => api.get(`/forms/${formCode}/saved-answers`),
};

export const formSubmissionService = {
  create: (formCode, data) => api.post(`/forms/${formCode}/submissions`, data),
  get: (submissionId, citizenId) =>
    api.get(`/forms/submissions/${submissionId}`, { params: { citizen_id: citizenId } }),
  update: (submissionId, data) => api.put(`/forms/submissions/${submissionId}`, data),
  complete: async (submissionId, data) => {
    const res = await api.post(`/forms/submissions/${submissionId}/complete`, data);
    invalidateClientCache("/citizens");
    invalidateClientCache("/forms");
    return res;
  },
  normalize: async (submissionId, data) => {
    const res = await api.post(`/forms/submissions/${submissionId}/normalize`, data);
    invalidateClientCache("/citizens");
    return res;
  },
};

export { api };
export default api;
