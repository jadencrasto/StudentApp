/**
 * src/lib/api.js
 * ──────────────
 * Axios instance pre-configured with:
 * - Base URL from env
 * - Automatic JWT header injection
 * - 401 → logout redirect
 */
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api/v1";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor: attach JWT ───────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("sais_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Response interceptor: handle auth errors ──────────────────────────────
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      // Only redirect for actual SAIS auth failures,
      // not for third-party credential issues (e.g. Google OAuth)
      const url = err.config?.url || '';
      const isClassroomRoute = url.includes('/classroom/');
      if (!isClassroomRoute) {
        localStorage.removeItem("sais_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────
export const authAPI = {
  register: (data) => api.post("/auth/register", data),
  login:    (data) => api.post("/auth/login", data),
  me:       ()     => api.get("/auth/me"),
};

// ── Assignments ───────────────────────────────────────────────────────────
export const assignmentsAPI = {
  list:           (params) => api.get("/assignments", { params }),
  create:         (data)   => api.post("/assignments", data),
  update:         (id, data) => api.patch(`/assignments/${id}`, data),
  remove:         (id)     => api.delete(`/assignments/${id}`),
};

// ── Attendance ────────────────────────────────────────────────────────────
export const attendanceAPI = {
  getSubjects: ()       => api.get("/attendance/subjects"),
  addSubject:  (data)   => api.post("/attendance/subjects", data),
  updateSubject: (id, data) => api.patch(`/attendance/subjects/${id}`, data),
  removeSubject: (id) => api.delete(`/attendance/subjects/${id}`),
  mark:        (data)   => api.post("/attendance/mark", data),
  summary:     ()       => api.get("/attendance/summary"),
  getHistory:  (id)     => api.get(`/attendance/history/${id}`),
};

// ── Activities ────────────────────────────────────────────────────────────
export const activitiesAPI = {
  list:   ()       => api.get("/activities"),
  create: (data)   => api.post("/activities", data),
  remove: (id)     => api.delete(`/activities/${id}`),
};

// ── Documents ─────────────────────────────────────────────────────────────
export const documentsAPI = {
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/documents/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  list:            ()   => api.get("/documents"),
  get:             (id) => api.get(`/documents/${id}`),
  saveAsAssignment:(id) => api.post(`/documents/${id}/save-as-assignment`),
  reprocess:       (id) => api.post(`/documents/${id}/re-process`),
};

// ── Alerts + Dashboard ────────────────────────────────────────────────────
export const alertsAPI = {
  list:      ()   => api.get("/alerts"),
  refresh:   ()   => api.post("/alerts/refresh"),
  markRead:  (id) => api.patch(`/alerts/${id}/read`),
  dashboard: ()   => api.get("/dashboard"),
};
