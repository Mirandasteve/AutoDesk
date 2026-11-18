import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi, TOKEN_KEY, USER_KEY } from '../services/api'

const AuthContext = createContext(null)

/**
 * Session state for the whole app.
 *
 * The JWT and a cached user profile are kept in localStorage so a page reload
 * does not force a re-login. On mount the cached token is verified against
 * GET /auth/me; if it has expired the axios interceptor has already cleared it,
 * and we drop the cached profile too.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const cached = localStorage.getItem(USER_KEY)
    return cached ? JSON.parse(cached) : null
  })
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [booting, setBooting] = useState(Boolean(localStorage.getItem(TOKEN_KEY)))
  const [sessionNotice, setSessionNotice] = useState(null)

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  // Verify a cached token on first load.
  useEffect(() => {
    let cancelled = false

    async function verify() {
      if (!localStorage.getItem(TOKEN_KEY)) {
        setBooting(false)
        return
      }
      try {
        const data = await authApi.me()
        if (!cancelled) {
          setUser(data.user ?? data)
          localStorage.setItem(USER_KEY, JSON.stringify(data.user ?? data))
        }
      } catch {
        if (!cancelled) clearSession()
      } finally {
        if (!cancelled) setBooting(false)
      }
    }

    verify()
    return () => {
      cancelled = true
    }
  }, [clearSession])

  // Surface an expired session once, rather than silently bouncing the user.
  useEffect(() => {
    function onExpired(event) {
      clearSession()
      setSessionNotice(event.detail || 'Your session expired. Please sign in again.')
    }
    window.addEventListener('autodesk:session-expired', onExpired)
    return () => window.removeEventListener('autodesk:session-expired', onExpired)
  }, [clearSession])

  const persist = useCallback((accessToken, profile) => {
    localStorage.setItem(TOKEN_KEY, accessToken)
    localStorage.setItem(USER_KEY, JSON.stringify(profile))
    setToken(accessToken)
    setUser(profile)
    setSessionNotice(null)
  }, [])

  const login = useCallback(
    async (email, password) => {
      const data = await authApi.login(email, password)
      const profile = data.user ?? {}
      persist(data.access_token, profile)
      return profile
    },
    [persist],
  )

  const register = useCallback(async (payload) => {
    const data = await authApi.register(payload)
    // Registration does not return a token; sign in straight away so the user
    // lands on their portal rather than back on the login form.
    const email = payload.email
    const password = payload.password
    return login(email, password)
  }, [login])

  const logout = useCallback(() => {
    clearSession()
    setSessionNotice(null)
  }, [clearSession])

  const value = useMemo(
    () => ({
      user,
      token,
      booting,
      isAuthenticated: Boolean(token && user),
      role: user?.role ?? null,
      sessionNotice,
      dismissNotice: () => setSessionNotice(null),
      login,
      register,
      logout,
      setUser,
    }),
    [user, token, booting, sessionNotice, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside <AuthProvider>.')
  }
  return context
}