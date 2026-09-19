import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api } from '@/lib/api'
import type { UserPublic } from '@/types/api'

export const TOKEN_STORAGE_KEY = 'rag_access_token'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface AuthContextValue {
  token: string | null
  user: UserPublic | null
  status: AuthStatus
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<UserPublic>
  logout: () => void
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    sessionStorage.getItem(TOKEN_STORAGE_KEY),
  )
  const [user, setUser] = useState<UserPublic | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
    setUser(null)
    setStatus('unauthenticated')
  }, [])

  useEffect(() => {
    let cancelled = false

    if (!token) {
      setStatus('unauthenticated')
      return
    }

    api
      .me(token)
      .then((restoredUser) => {
        if (cancelled) return
        setUser(restoredUser)
        setStatus('authenticated')
      })
      .catch(() => {
        if (cancelled) return
        clearSession()
      })

    return () => {
      cancelled = true
    }
    // Only re-validate when the token itself changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password)
    const loggedInUser = await api.me(result.access_token)
    sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token)
    setToken(result.access_token)
    setUser(loggedInUser)
    setStatus('authenticated')
  }, [])

  const register = useCallback((email: string, password: string) => api.register(email, password), [])

  const logout = useCallback(() => {
    clearSession()
  }, [clearSession])

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, status, login, register, logout }),
    [token, user, status, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
