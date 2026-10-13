import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - attach JWT token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('sais_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor - handle 401 errors globally
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Only redirect to login for actual SAIS auth failures,
      // not for third-party credential issues (e.g. Google OAuth)
      const url = error.config?.url || '';
      const isClassroomRoute = url.includes('/classroom/');
      if (!isClassroomRoute) {
        localStorage.removeItem('sais_token');
        localStorage.removeItem('sais_user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const api = client;

// ── Grouped API objects (kept for backwards compatibility) ───────────────────
export const authAPI = {
  register: (data) => client.post('/auth/register', data),
  login:    (data) => client.post('/auth/login', data),
  me:       ()     => client.get('/auth/me'),
};

export const assignmentsAPI = {
  list:           (params) => client.get('/assignments', { params }),
  create:         (data)   => client.post('/assignments', data),
  update:         (id, data) => client.patch(`/assignments/${id}`, data),
  remove:         (id)     => client.delete(`/assignments/${id}`),
};

export const attendanceAPI = {
  getSubjects: ()       => client.get('/attendance/subjects'),
  addSubject:  (data)   => client.post('/attendance/subjects', data),
  updateSubject: (id, data) => client.patch(`/attendance/subjects/${id}`, data),
  removeSubject: (id) => client.delete(`/attendance/subjects/${id}`),
  mark:        (data)   => client.post('/attendance/mark', data),
  summary:     ()       => client.get('/attendance/summary'),
  getHistory:  (id)     => client.get(`/attendance/history/${id}`),
};

export const activitiesAPI = {
  list:   ()       => client.get('/activities'),
  create: (data)   => client.post('/activities', data),
  remove: (id)     => client.delete(`/activities/${id}`),
};

export const documentsAPI = {
  upload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return client.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  list:            ()   => client.get('/documents'),
  get:             (id) => client.get(`/documents/${id}`),
  saveAsAssignment:(id) => client.post(`/documents/${id}/save-as-assignment`),
  reprocess:       (id) => client.post(`/documents/${id}/re-process`),
};

export const alertsAPI = {
  list:      ()   => client.get('/alerts'),
  refresh:   ()   => client.post('/alerts/refresh'),
  markRead:  (id) => client.patch(`/alerts/${id}/read`),
  dashboard: ()   => client.get('/dashboard'),
};

export default client;
