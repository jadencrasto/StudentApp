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
  register:       (data) => client.post('/auth/register', data),
  login:          (data) => client.post('/auth/login', data),
  me:             ()     => client.get('/auth/me'),
  changePassword: (data) => client.post('/auth/change-password', data),
};

export const institutionsAPI = {
  // Super Admin
  listInstitutions:           () => client.get('/super-admin/institutions'),
  listInstitutionsWithCounts: () => client.get('/super-admin/institutions-with-counts'),
  createInstitution:          (data) => client.post('/super-admin/institutions', data),
  deactivateInstitution:      (id) => client.patch(`/super-admin/institutions/${id}/deactivate`),
  createAdmin:                (id, data) => client.post(`/super-admin/institutions/${id}/admins`, data),
  listAdmins:                 () => client.get('/super-admin/admins'),
  deactivateAdmin:            (id) => client.patch(`/super-admin/admins/${id}/deactivate`),
  reactivateAdmin:            (id) => client.patch(`/super-admin/admins/${id}/reactivate`),
  resetAdminPassword:         (id) => client.post(`/super-admin/admins/${id}/reset-password`),

  // Institution Admin
  listCohorts:                (params) => client.get('/admin/cohorts', { params }),
  createCohort:               (data) => client.post('/admin/cohorts', data),
  updateCohort:               (id, data) => client.patch(`/admin/cohorts/${id}`, data),
  deactivateCohort:           (id) => client.patch(`/admin/cohorts/${id}/deactivate`),
  regenerateCohortJoinCode:   (id) => client.post(`/admin/cohorts/${id}/regenerate-join-code`),
  toggleCohortJoinCode:       (id) => client.patch(`/admin/cohorts/${id}/toggle-join-code`),
  regenerateJoinCode:         () => client.post('/admin/institution/regenerate-join-code'),
  listJoinRequests:           (params) => client.get('/admin/join-requests', { params }),
  decideJoinRequest:          (id, data) => client.post(`/admin/join-requests/${id}/decide`, data),
};

export const adminStudentsAPI = {
  list:             (params) => client.get('/admin/students', { params }),
  create:           (data) => client.post('/admin/students', data),
  downloadTemplate: () => client.get('/admin/students/template', { responseType: 'blob' }),
  uploadPreview:    (file) => {
    const form = new FormData();
    form.append('file', file);
    return client.post('/admin/students/upload-preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  uploadConfirm:    (data) => client.post('/admin/students/upload-confirm', data),
  downloadErrorReport: (badRows) => client.post('/admin/students/error-report', badRows, { responseType: 'blob' }),
  resetPassword:    (studentId) => client.post(`/admin/students/${studentId}/reset-password`),
  deactivate:       (studentId) => client.patch(`/admin/students/${studentId}/deactivate`),
  reactivate:       (studentId) => client.patch(`/admin/students/${studentId}/reactivate`),
  moveCohort:       (studentId, cohortId) => client.patch(`/admin/students/${studentId}/move-cohort`, { cohort_id: cohortId }),
};

export const studentAPI = {
  updateProfile: (data) => client.patch('/me/profile', data),
  join:          (data) => client.post('/join', data),
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
