/**
 * Secure Authentication Service
 * 
 * SECURITY FIX: Uses httpOnly secure cookies instead of localStorage
 * to prevent XSS attacks. Tokens are never exposed to JavaScript.
 * 
 * The backend MUST set:
 * - Set-Cookie: auth_token=<token>; HttpOnly; Secure; SameSite=Lax; Path=/
 * - Set-Cookie: auth_token=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0  (for logout)
 */

// Helper: Get API base URL (dev vs prod)
export function getAPIBase() {
  if (typeof window === 'undefined') return ''
  const configuredBase = String(import.meta?.env?.VITE_API_BASE_URL || '').trim()
  if (configuredBase) {
    return configuredBase.replace(/\/$/, '')
  }
  // In development on localhost, always use backend at :8000
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    const configuredPort = String(import.meta?.env?.VITE_API_PORT || '').trim()
    const apiPort = configuredPort || (window.location.port === '5173' ? '8001' : '8000')
    return `${window.location.protocol}//${window.location.hostname}:${apiPort}`
  }
  // In production (same origin)
  return window.location.origin
}

export function getWebSocketBase() {
  const apiBase = getAPIBase()
  if (apiBase.startsWith('https://')) {
    return apiBase.replace('https://', 'wss://')
  }
  return apiBase.replace('http://', 'ws://')
}

class AuthService {
  /**
   * Register a new user.
   * @param {string} username 
   * @param {string} password 
   * @returns {Promise<{ok: boolean, error?: string}>}
   */
  static async register(username, password, email = null) {
    try {
      const res = await fetch(`${getAPIBase()}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, email }),
        credentials: 'include', // Include cookies
      })
      if (!res.ok) {
        const error = await res.json()
        return { ok: false, error: error.detail || 'Registration failed' }
      }
      return { ok: true }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  }

  /**
   * Login user. Credentials are sent to backend, which sets httpOnly cookie.
   * @param {string} username 
   * @param {string} password 
   * @returns {Promise<{ok: boolean, error?: string}>}
   */
  static async login(username, password) {
    try {
      const res = await fetch(`${getAPIBase()}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        credentials: 'include', // Include & accept cookies
      })
      if (!res.ok) {
        const error = await res.json()
        return { ok: false, error: error.detail || 'Login failed' }
      }
      // Cookie is automatically set by browser; no token in JS
      return { ok: true }
    } catch (e) {
      return { ok: false, error: e.message }
    }
  }

  /**
   * Get current user info. Token is in httpOnly cookie (automatic).
   * @returns {Promise<{username?: string, error?: string}>}
   */
  static async getMe() {
    try {
      const res = await fetch(`${getAPIBase()}/auth/me`, {
        credentials: 'include', // Include httpOnly cookies
      })
      if (!res.ok) {
        return {} // Not logged in
      }
      const text = await res.text()
      if (!text) {
        return {} // Empty response
      }
      return JSON.parse(text)
    } catch (e) {
      return {}
    }
  }

  /**
   * Logout user. Backend clears the httpOnly cookie.
   * @returns {Promise<{ok: boolean}>}
   */
  static async logout() {
    try {
      // POST to logout endpoint (should be created in backend)
      const res = await fetch(`${getAPIBase()}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
      return { ok: res.ok }
    } catch (e) {
      return { ok: false }
    }
  }

  /**
   * Check if user is authenticated (by attempting to fetch /auth/me).
   * @returns {Promise<boolean>}
   */
  static async isAuthenticated() {
    const user = await this.getMe()
    return !!user.username
  }
}

export default AuthService
