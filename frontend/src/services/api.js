/**
 * Typed HTTP client for the AutoDesk API.
 *
 * Every backend response uses the envelope
 *   { success: boolean, message: string, data?: any, error?: string, fields?: object }
 * so unwrapping happens once, here, instead of in every component.
 */
import axios from 'axios'

export const TOKEN_KEY = 'autodesk.token'
export const USER_KEY = 'autodesk.user'

export class ApiError extends Error {
  constructor(message, { status, error, fields } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status ?? 0
    this.error = error ?? 'error'
    this.fields = fields ?? {}
  }
}

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/**
 * On a 401 the stored session is stale (expired or revoked), so clear it and
 * let the router's RequireAuth component send the user back to the login page.
 * The `X-Auth-Expired` header lets the UI show "session expired" rather than a
 * bare "please log in".
 */
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && localStorage.getItem(TOKEN_KEY)) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      if (!window.location.pathname.startsWith('/login')) {
        window.dispatchEvent(
          new CustomEvent('autodesk:session-expired', { detail: error.response.data?.message }),
        )
      }
    }
    return Promise.reject(error)
  },
)

function unwrap(response) {
  const body = response.data ?? {}
  return body.data !== undefined ? body.data : body
}

async function request(config) {
  try {
    const response = await http(config)
    return unwrap(response)
  } catch (error) {
    if (error.response) {
      const { status, data } = error.response
      throw new ApiError(data?.message || 'The request failed.', {
        status,
        error: data?.error,
        fields: data?.fields,
      })
    }
    if (error.code === 'ECONNABORTED') {
      throw new ApiError('The server took too long to respond. Please try again.', {
        error: 'timeout',
      })
    }
    throw new ApiError('Cannot reach the AutoDesk API. Is the backend running on port 5000?', {
      error: 'network_error',
    })
  }
}

export const api = {
  get: (url, params) => request({ method: 'get', url, params }),
  post: (url, data) => request({ method: 'post', url, data }),
  patch: (url, data) => request({ method: 'patch', url, data }),
  del: (url) => request({ method: 'delete', url }),
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const authApi = {
  login: (email, password) => request({ method: 'post', url: '/auth/login', data: { email, password } }),
  register: (payload) => request({ method: 'post', url: '/auth/register', data: payload }),
  me: () => request({ method: 'get', url: '/auth/me' }),
  stats: () => request({ method: 'get', url: '/auth/stats' }),
  registrationPolicy: () => request({ method: 'get', url: '/auth/registration-policy' }),
  logout: () => request({ method: 'post', url: '/auth/logout' }),
  passwordStrength: (password) =>
    request({ method: 'post', url: '/auth/password-strength', data: { password } }),
  changePassword: (currentPassword, newPassword) =>
    request({
      method: 'patch',
      url: '/auth/password',
      data: { current_password: currentPassword, new_password: newPassword },
    }),
}

// ---------------------------------------------------------------------------
// Metadata (public) - drives every dropdown so the UI can never offer a value
// the API would reject.
// ---------------------------------------------------------------------------
export const metaApi = {
  get: () => request({ method: 'get', url: '/meta' }),
  health: () => request({ method: 'get', url: '/health' }),
}

// ---------------------------------------------------------------------------
// Tickets
// ---------------------------------------------------------------------------
export const ticketApi = {
  create: (payload) => request({ method: 'post', url: '/tickets', data: payload }),
  list: (params) => request({ method: 'get', url: '/tickets', params }),
  mine: (params) => request({ method: 'get', url: '/tickets/my', params }),
  get: (id) => request({ method: 'get', url: `/tickets/${id}` }),
  update: (id, payload) => request({ method: 'patch', url: `/tickets/${id}`, data: payload }),
  addNotes: (id, notes) =>
    request({ method: 'post', url: `/tickets/${id}/notes`, data: { notes } }),
  metadata: () => request({ method: 'get', url: '/tickets/metadata' }),
  lookup: (description, title) =>
    request({ method: 'post', url: '/tickets/lookup', data: { description, title } }),
  claim: (id) => request({ method: 'post', url: `/tickets/${id}/claim` }),
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------
export const agentApi = {
  dashboard: () => request({ method: 'get', url: '/agent/dashboard' }),
  tickets: (params) => request({ method: 'get', url: '/agent/tickets', params }),
  mine: (params) => request({ method: 'get', url: '/agent/my-tickets', params }),
  get: (id) => request({ method: 'get', url: `/agent/tickets/${id}` }),
  setStatus: (id, payload) =>
    request({ method: 'patch', url: `/agent/tickets/${id}/status`, data: payload }),
  claim: (id) => request({ method: 'post', url: `/agent/tickets/${id}/claim` }),
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------
export const adminApi = {
  dashboard: () => request({ method: 'get', url: '/admin/dashboard' }),
  analytics: () => request({ method: 'get', url: '/admin/analytics' }),
  tickets: (params) => request({ method: 'get', url: '/admin/tickets', params }),
  ticket: (id) => request({ method: 'get', url: `/admin/tickets/${id}` }),
  users: (params) => request({ method: 'get', url: '/admin/users', params }),
  user: (id) => request({ method: 'get', url: `/admin/users/${id}` }),
  updateUser: (id, payload) => request({ method: 'patch', url: `/admin/users/${id}`, data: payload }),
  sla: () => request({ method: 'get', url: '/admin/sla' }),
  slaScan: () => request({ method: 'post', url: '/admin/sla/scan' }),
  reports: () => request({ method: 'get', url: '/admin/reports' }),
  mlStatus: () => request({ method: 'get', url: '/admin/ml-status' }),
  // `updatePriority` also re-runs the priority engine; without it the backend
  // only refreshes category, team and confidence, leaving human triage intact.
  reclassify: (id, updatePriority) =>
    request({
      method: 'post',
      url: `/admin/reclassify/${id}`,
      params: updatePriority ? { update_priority: 1 } : undefined,
    }),
  system: () => request({ method: 'get', url: '/admin/system' }),
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------
export const notificationApi = {
  list: (params) => request({ method: 'get', url: '/notifications', params }),
  unreadCount: () => request({ method: 'get', url: '/notifications/unread-count' }),
  markRead: (id) => request({ method: 'patch', url: `/notifications/${id}/read` }),
  markAllRead: () => request({ method: 'patch', url: '/notifications/read-all' }),
}