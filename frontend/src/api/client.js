import axios from 'axios';

const client = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/v1',
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

export default client;
