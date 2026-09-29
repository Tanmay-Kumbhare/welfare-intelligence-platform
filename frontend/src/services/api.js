import axios from "axios";

import { attachAuthHeaders } from "./auth";

const API_URL = import.meta.env.VITE_API_URL || "/api/v1";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Auto-attach auth headers to any request that goes through the main api
// client. Public endpoints still work; protected endpoints receive the
// current token automatically.
api.interceptors.request.use(attachAuthHeaders);

// Auth-specific client keeps its own interceptors separate so login/register
// requests never get polluted by a stale token.
export const authApi = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// NOTE: me/logout go through the main `api` client so the Authorization
// header is attached automatically. Only register/login use `authApi`.

// Public scheme catalogue is still open for browsing.
// Authenticated user-scoped endpoints are added below.
export const citizenService = {
  register: (data) => api.post("/citizens/", data),
  get: (id) => api.get(`/citizens/${id}`),
  update: (id, data) => api.put(`/citizens/${id}`, data),
};

export const authService = {
  register: (data) => authApi.post("/auth/register", data),
  login: (data) => authApi.post("/auth/login", data),
  me: () => api.get("/auth/me"),
  logout: () => api.post("/auth/logout"),
};

export const schemeService = {
  getAll: () => api.get("/schemes/"),
  get: (id) => api.get(`/schemes/${id}`),
};

export const eligibilityService = {
  evaluate: (citizenId) => api.post(`/eligibility/evaluate/${citizenId}`),
};

export const recommendationService = {
  getForCitizen: (citizenId) => api.get(`/recommendations/${citizenId}`),
};

// Phase 2C: database-driven dynamic form. The form definition (sections,
// questions, options, conditions) and the submission lifecycle all come from
// the backend — no question data is duplicated in the frontend.
export const formService = {
  getActive: (formCode) => api.get(`/forms/${formCode}`),
  // Profile-derived values for prefilling the form (authenticated users).
  getPrefill: (formCode) => api.get(`/forms/${formCode}/prefill`),
  // Everything the citizen already answered (their own latest submission).
  getSavedAnswers: (formCode) => api.get(`/forms/${formCode}/saved-answers`),
};

export const formSubmissionService = {
  create: (formCode, data) => api.post(`/forms/${formCode}/submissions`, data),
  get: (submissionId, citizenId) =>
    api.get(`/forms/submissions/${submissionId}`, { params: { citizen_id: citizenId } }),
  update: (submissionId, data) => api.put(`/forms/submissions/${submissionId}`, data),
  complete: (submissionId, data) =>
    api.post(`/forms/submissions/${submissionId}/complete`, data),
  normalize: (submissionId, data) =>
    api.post(`/forms/submissions/${submissionId}/normalize`, data),
};

// Named export too, so feature pages can `import { api } from "../../services/api"`
// without rebinding the default.
export { api };

export default api;
