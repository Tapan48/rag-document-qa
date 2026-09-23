import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '@/context/AuthContext'
import { api, ApiError } from '@/lib/api'
import { RegisterPage } from '@/pages/RegisterPage'

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

function renderPage() {
  return render(<MemoryRouter><AuthProvider><RegisterPage /></AuthProvider></MemoryRouter>)
}

describe('RegisterPage registration availability', () => {
  it('does not show the form before availability is known', () => {
    vi.spyOn(api, 'authConfig').mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status')).toHaveTextContent(/checking registration/i)
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument()
  })

  it('shows invite-only access for direct visits when disabled', async () => {
    vi.spyOn(api, 'authConfig').mockResolvedValue({ registration_enabled: false })
    renderPage()
    expect(await screen.findByText('Invite-only access')).toBeVisible()
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login')
  })

  it('keeps the form hidden on configuration failure', async () => {
    vi.spyOn(api, 'authConfig').mockRejectedValue(new Error('Unavailable'))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not check/i)
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument()
  })

  it('explains access when the backend disables registration after the form loads', async () => {
    vi.spyOn(api, 'authConfig').mockResolvedValue({ registration_enabled: true })
    vi.spyOn(api, 'register').mockRejectedValue(new ApiError(403, 'Registration is invite-only'))
    const user = userEvent.setup()
    renderPage()
    await user.type(await screen.findByLabelText(/email/i), 'reviewer@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'test-password')
    await user.click(screen.getByRole('button', { name: /register/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/access is by invitation/i)
  })
})
