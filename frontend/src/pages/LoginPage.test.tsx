import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/context/AuthContext'
import { api, ApiError } from '@/lib/api'
import { LoginPage } from '@/pages/LoginPage'

beforeEach(() => {
  vi.spyOn(api, 'authConfig').mockResolvedValue({ registration_enabled: true })
})

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  it('shows the register link when registration is enabled', async () => {
    renderLoginPage()
    expect(await screen.findByRole('link', { name: /register/i })).toHaveAttribute('href', '/register')
  })

  it('hides registration for invite-only access while keeping login available', async () => {
    vi.mocked(api.authConfig).mockResolvedValue({ registration_enabled: false })
    renderLoginPage()
    expect(await screen.findByText(/access is by invitation/i)).toBeVisible()
    expect(screen.queryByRole('link', { name: /register/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled()
  })

  it('keeps login available when registration configuration cannot load', async () => {
    vi.mocked(api.authConfig).mockRejectedValue(new TypeError('Failed to fetch'))
    renderLoginPage()
    await waitFor(() => expect(api.authConfig).toHaveBeenCalled())
    expect(screen.queryByRole('link', { name: /register/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled()
  })

  it('shows a validation error for incorrect credentials without navigating away', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new ApiError(401, 'Incorrect email or password'))
    const user = userEvent.setup()

    renderLoginPage()
    await waitFor(() => expect(screen.getByLabelText(/email/i)).toBeEnabled())

    await user.type(screen.getByLabelText(/email/i), 'a@example.com')
    await user.type(screen.getByLabelText(/password/i), 'wrongpassword')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect email or password/i)
  })

  it('shows a generic message when the server is unreachable', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new TypeError('Failed to fetch'))
    const user = userEvent.setup()

    renderLoginPage()
    await waitFor(() => expect(screen.getByLabelText(/email/i)).toBeEnabled())

    await user.type(screen.getByLabelText(/email/i), 'a@example.com')
    await user.type(screen.getByLabelText(/password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i)
  })
})
