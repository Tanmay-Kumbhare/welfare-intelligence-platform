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
  get: (id) => {
    if (!id || id === "null" || id === "undefined") {
      return Promise.reject(new Error("Invalid citizen ID"));
    }
    return cachedGet(api, `/citizens/${id}`);
  },
  update: async (id, data) => {
    if (!id || id === "null" || id === "undefined") {
      return Promise.reject(new Error("Invalid citizen ID"));
    }
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
  stats: () => api.get("/admin/stats"),
  listSchemes: () => api.get("/admin/schemes"),
  schemeDetail: (schemeId) => api.get(`/admin/schemes/${schemeId}`),
  createScheme: (data) => api.post("/admin/schemes", data),
  updateScheme: (schemeId, data) => api.patch(`/admin/schemes/${schemeId}`, data),
  archiveScheme: (schemeId) => api.post(`/admin/schemes/${schemeId}/archive`),
  restoreScheme: (schemeId) => api.post(`/admin/schemes/${schemeId}/restore`),
  deleteScheme: (schemeId) => api.delete(`/admin/schemes/${schemeId}`),
  verifyScheme: (schemeId, verifiedOn) =>
    api.post(`/admin/schemes/${schemeId}/verify`, { verified_on: verifiedOn }),
  listRuleGroups: (schemeId) => api.get(`/admin/schemes/${schemeId}/rule-groups`),
  createRuleGroup: (schemeId, data) =>
    api.post(`/admin/schemes/${schemeId}/rule-groups`, data),
  updateRuleGroup: (schemeId, groupId, data) =>
    api.patch(`/admin/schemes/${schemeId}/rule-groups/${groupId}`, data),
  deleteRuleGroup: (schemeId, groupId) =>
    api.delete(`/admin/schemes/${schemeId}/rule-groups/${groupId}`),
  setGroupCombiningOperator: (schemeId, groupCombiningOperator) =>
    api.patch(`/admin/schemes/${schemeId}/group-combining-operator`, {
      group_combining_operator: groupCombiningOperator,
    }),
  createRule: (schemeId, data) => api.post(`/admin/schemes/${schemeId}/rules`, data),
  updateRule: (schemeId, ruleId, data) =>
    api.patch(`/admin/schemes/${schemeId}/rules/${ruleId}`, data),
  deleteRule: (schemeId, ruleId) =>
    api.delete(`/admin/schemes/${schemeId}/rules/${ruleId}`),
  listDocuments: (schemeId) => api.get(`/admin/schemes/${schemeId}/documents`),
  createDocument: (schemeId, data) =>
    api.post(`/admin/schemes/${schemeId}/documents`, data),
  updateDocument: (schemeId, documentId, data) =>
    api.patch(`/admin/schemes/${schemeId}/documents/${documentId}`, data),
  deleteDocument: (schemeId, documentId) =>
    api.delete(`/admin/schemes/${schemeId}/documents/${documentId}`),
  listSchemeSourceDocuments: (schemeId) =>
    api.get(`/admin/schemes/${schemeId}/source-documents`),
  linkSchemeSourceDocument: (schemeId, sourceDocumentId) =>
    api.put(`/admin/schemes/${schemeId}/source-documents/${sourceDocumentId}`),
  unlinkSchemeSourceDocument: (schemeId, sourceDocumentId) =>
    api.delete(`/admin/schemes/${schemeId}/source-documents/${sourceDocumentId}`),
  rulesWithProvenance: (schemeId) =>
    api.get(`/admin/schemes/${schemeId}/rules-with-provenance`),
  latestDocumentSentences: (schemeId, query) =>
    api.get(`/admin/provenance/schemes/${schemeId}/latest-document-sentences`, {
      params: query ? { query } : {},
    }),
  documentSentences: (sourceDocumentId, query) =>
    api.get(`/admin/provenance/documents/${sourceDocumentId}/sentences`, {
      params: query ? { query } : {},
    }),
  linkRuleProvenance: (ruleId, sourceDocumentId, sentenceIndex) =>
    api.post(`/admin/provenance/rules/${ruleId}/link`, {}, {
      params: { source_document_id: sourceDocumentId, sentence_index: sentenceIndex },
    }),
  verifyRuleProvenance: (ruleId, provenanceId) =>
    api.post(`/admin/provenance/rules/${ruleId}/links/${provenanceId}/verify`),
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

export const documentService = {
  getRequirements: (citizenId) => {
    if (!citizenId || citizenId === "null" || citizenId === "undefined") {
      return Promise.reject(new Error("Citizen ID is required to get document requirements"));
    }
    return api.get(`/documents/requirements/${citizenId}`);
  },
  upload: async (citizenId, data) => {
    if (!citizenId || citizenId === "null" || citizenId === "undefined") {
      return Promise.reject(new Error("Citizen ID is required to upload a document"));
    }
    const res = await api.post(`/documents/upload/${citizenId}`, data);
    invalidateClientCache(`/citizens/${citizenId}`);
    return res;
  },
  delete: async (citizenId, documentId) => {
    if (!citizenId || !documentId) {
      return Promise.reject(new Error("Citizen ID and Document ID are required to delete a document"));
    }
    const res = await api.delete(`/documents/${citizenId}/${documentId}`);
    invalidateClientCache(`/citizens/${citizenId}`);
    return res;
  },
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
