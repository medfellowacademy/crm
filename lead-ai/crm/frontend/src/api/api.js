import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://medfellow-crm-api.onrender.com';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Redirect to login if server returns 401 (expired or invalid token).
// We clear localStorage directly here because the interceptor runs outside
// React's render cycle (no access to AuthContext).  AuthContext reads from
// localStorage on mount and will reflect the cleared state after redirect.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  login: (username, password) =>
    api.post('/api/auth/login', { username, password }),
  logout: () => {
    localStorage.removeItem('user');
    window.location.href = '/login';
  },
};

// Leads API
export const leadsAPI = {
  getAll: (params) => api.get('/api/leads', { params }),
  getById: (leadId) => api.get(`/api/leads/${leadId}`),
  create: (data) => api.post('/api/leads', data),
  update: (leadId, data) => api.put(`/api/leads/${leadId}`, data),
  delete: (leadId) => api.delete(`/api/leads/${leadId}`),
  bulkUpdate: (leadIds, updates) => api.post('/api/leads/bulk-update', { lead_ids: leadIds, updates }),
  
  // Notes
  getNotes: (leadId) => api.get(`/api/leads/${leadId}/notes`),
  addNote: (leadId, data) => api.post(`/api/leads/${leadId}/notes`, data),
  
  // Communication
  sendWhatsApp: (leadId, message) => api.post(`/api/leads/${leadId}/send-whatsapp`, { message }),
  sendEmail: (leadId, subject, body) => api.post(`/api/leads/${leadId}/send-email`, { subject, body }),

  // Live Chat
  getChatMessages: (leadId) => api.get(`/api/leads/${leadId}/chat`),
  sendChatMessage: (leadId, data) => api.post(`/api/leads/${leadId}/chat`, data),
};

// Upload API
export const uploadAPI = {
  uploadFile: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/api/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  },
};

// Dashboard API
export const dashboardAPI = {
  getStats: () => api.get('/api/dashboard/stats'),
  getFollowupsToday: (assignedTo) =>
    api.get('/api/leads/followups/today', assignedTo ? { params: { assigned_to: assignedTo } } : {}),
  getNotifications: () => api.get('/api/notifications'),
};

// Analytics API
export const analyticsAPI = {
  getRevenueByCountry: () => api.get('/api/analytics/revenue-by-country'),
  getConversionFunnel: () => api.get('/api/analytics/conversion-funnel'),
};

// Hospitals API
export const hospitalsAPI = {
  getAll: (params) => api.get('/api/hospitals', { params }),
  create: (data) => api.post('/api/hospitals', data),
};

// Courses API
export const coursesAPI = {
  getAll: (params) => api.get('/api/courses', { params }),
  create: (data) => api.post('/api/courses', data),
};

// Counselors API
export const counselorsAPI = {
  getAll: () => api.get('/api/counselors'),
  getPerformance: () => api.get('/api/counselors/performance'),
};

// Users API
export const usersAPI = {
  getAll: () => api.get('/api/users'),
  getById: (userId) => api.get(`/api/users/${userId}`),
  create: (data) => api.post('/api/users', data),
  update: (userId, data) => api.put(`/api/users/${userId}`, data),
  delete: (userId) => api.delete(`/api/users/${userId}`),
};

export default api;
