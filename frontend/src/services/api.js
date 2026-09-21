import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "/api/v1";

const api = axios.create({
  baseURL: API_URL,
});

export const citizenService = {
  register: (data) => api.post("/citizens/", data),
  get: (id) => api.get(`/citizens/${id}`),
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

export default api;