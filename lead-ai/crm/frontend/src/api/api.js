import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://medfellow-crm-api.onrender.com';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,          // 15 s — prevents requests hanging indefinitely
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach the JWT token from localStorage to every outgoing request.
api.interceptors.request.use((config) => {
  try {
    const stored = localStorage.getItem('user');
    const token = stored ? JSON.parse(stored)?.token : null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // localStorage unavailable or JSON malformed — continue without token
  }
  return config;
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
  bulkCreate: (leads) => api.post('/api/leads/bulk-create', leads),
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
  update: (id, data) => api.put('/api/hospitals/' + id, data),
  delete: (id) => api.delete('/api/hospitals/' + id),
};

// Courses API
export const coursesAPI = {
  getAll: (params) => api.get('/api/courses', { params }),
  create: (data) => api.post('/api/courses', data),
  update: (id, data) => api.put('/api/courses/' + id, data),
  delete: (id) => api.delete('/api/courses/' + id),
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
  resetPassword: (userId, newPassword) => api.put(`/api/users/${userId}/admin-reset-password`, { new_password: newPassword }),
};


// Admin API
export const adminAPI = {
  getStats: () => api.get('/api/admin/stats'),
  getTeamPerformance: () => api.get('/api/admin/team-performance'),
  getFunnelAnalysis: () => api.get('/api/admin/funnel-analysis'),
  getRevenueTrend: (days = 30) => api.get(`/api/admin/revenue-trend?days=${days}`),
};

// User Stats API
export const userStatsAPI = {
  getStats: (userId) => api.get(`/api/users/${userId}/stats`),
  getPerformance: (userId, days = 7) => api.get(`/api/users/${userId}/performance?days=${days}`),
  changePassword: (userId, data) => api.put(`/api/users/${userId}/password`, data),
};

// Notification actions API
export const notificationActionsAPI = {
  markRead: (id) => api.patch(`/api/notifications/${id}/read`),
  snooze: (id, hours = 1) => api.patch(`/api/notifications/${id}/snooze?hours=${hours}`),
  markAllRead: () => api.post('/api/notifications/read-all'),
};

// AI Search API
export const aiSearchAPI = {
  search: (query) => api.post('/api/ai/search', { query }),
};

// Source Attribution API
export const sourceAnalyticsAPI = {
  getSourceAnalytics: () => api.get('/api/admin/source-analytics'),
};

// Conversion Time API
export const conversionTimeAPI = {
  getConversionTime: () => api.get('/api/admin/conversion-time'),
};

// Cohort Analysis API
export const cohortAPI = {
  getCohorts: () => api.get('/api/admin/cohort-analysis'),
};

// SLA API
export const slaAPI = {
  getConfig:     ()     => api.get('/api/admin/sla-config'),
  updateConfig:  (data) => api.put('/api/admin/sla-config', data),
  getCompliance: ()     => api.get('/api/admin/sla-compliance'),
};

// Call Timing API
export const callTimingAPI = {
  getCallTiming: (country) =>
    api.get('/api/analytics/call-timing', country ? { params: { country } } : {}),
};

// Duplicate Detection API
export const duplicatesAPI = {
  check:  (data)    => api.post('/api/leads/check-duplicates', data),
  merge:  (payload) => api.post('/api/leads/merge', payload),
};

// Score Decay Engine API
export const decayAPI = {
  getConfig:   ()       => api.get('/api/admin/decay-config'),
  updateConfig:(data)   => api.put('/api/admin/decay-config', data),
  runNow:      ()       => api.post('/api/admin/run-decay'),
  getLog:      (params) => api.get('/api/admin/decay-log', { params }),
  getPreview:  ()       => api.get('/api/admin/decay-preview'),
};

// WhatsApp Template Library API
export const waTemplatesAPI = {
  list:        (category) => api.get('/api/wa-templates', category ? { params: { category } } : {}),
  create:      (data)     => api.post('/api/wa-templates', data),
  update:      (id, data) => api.put(`/api/wa-templates/${id}`, data),
  delete:      (id)       => api.delete(`/api/wa-templates/${id}`),
  send:        (leadId, payload) => api.post(`/api/leads/${leadId}/send-wa-template`, payload),
};


export default api;
