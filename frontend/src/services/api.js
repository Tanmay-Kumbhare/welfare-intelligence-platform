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

export default api;
