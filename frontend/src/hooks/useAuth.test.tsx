import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, TOKEN_STORAGE_KEY } from '@/context/AuthContext'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import type { UserPublic } from '@/types/api'

const USER: UserPublic = { id: 'u1', is_admin: false, email: 'a@example.com', created_at: '2026-01-01T00:00:00Z' }

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('useAuth / AuthProvider', () => {
  it('starts unauthenticated when there is no stored token', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.status).toBe('unauthenticated'))
    expect(result.current.user).toBeNull()
  })

  it('restores a session by validating the stored token against /auth/me', async () => {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
    vi.spyOn(api, 'me').mockResolvedValue(USER)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user).toEqual(USER)
    expect(api.me).toHaveBeenCalledWith('stored-token')
  })

  it('clears an invalid/expired stored token instead of staying authenticated', async () => {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, 'expired-token')
    vi.spyOn(api, 'me').mockRejectedValue(new Error('401'))

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.status).toBe('unauthenticated'))
    expect(result.current.token).toBeNull()
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
  })

  it('login stores the token and loads the user', async () => {
    vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'new-token', token_type: 'bearer' })
    vi.spyOn(api, 'me').mockResolvedValue(USER)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'))

    await act(async () => {
      await result.current.login('a@example.com', 'password123')
    })

    expect(result.current.status).toBe('authenticated')
    expect(result.current.user).toEqual(USER)
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBe('new-token')
  })

  it('logout clears the token, user, and sessionStorage', async () => {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token')
    vi.spyOn(api, 'me').mockResolvedValue(USER)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('authenticated'))

    act(() => {
      result.current.logout()
    })

    expect(result.current.status).toBe('unauthenticated')
    expect(result.current.user).toBeNull()
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
  })
})
