import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, AuthProvider, type AuthContextValue } from '@/context/AuthContext'
import { api, ApiError } from '@/lib/api'
import { RequestAccessPage } from '@/pages/RequestAccessPage'
import { AccessRequestsPage } from '@/pages/AccessRequestsPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { LoginPage } from '@/pages/LoginPage'
import type { AccessRequestPublic } from '@/types/api'

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear() })
const approval = () => vi.spyOn(api, 'authConfig').mockResolvedValue({ registration_enabled: false, registration_mode: 'approval' })
const context = (admin: boolean): AuthContextValue => ({ token: 'test-token', status: 'authenticated', user: { id: 'owner', email: 'owner@example.com', is_admin: admin, created_at: '' }, login: vi.fn(), register: vi.fn(), logout: vi.fn() })
const pending: AccessRequestPublic = { id: 'r1', email: 'reviewer@example.com', status: 'pending', created_at: '2026-09-24T00:00:00Z', expires_at: null, deliveries: [] }

function adminPage(admin = true) {
  return render(<MemoryRouter><AuthContext.Provider value={context(admin)}><AccessRequestsPage /></AuthContext.Provider></MemoryRouter>)
}
function registrationPage(token?: string) {
  return render(<MemoryRouter initialEntries={['/register' + (token ? '#token=' + token : '')]}><AuthProvider><RegisterPage /></AuthProvider></MemoryRouter>)
}

describe('access request flow', () => {
  it('links to request access from login', async () => {
    approval()
    render(<MemoryRouter><AuthProvider><LoginPage /></AuthProvider></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /request access/i })).toHaveAttribute('href', '/request-access')
    expect(screen.queryByRole('link', { name: /^register$/i })).not.toBeInTheDocument()
  })
  it('submits an email and shows a non-enumerating confirmation', async () => {
    approval()
    const submit = vi.spyOn(api, 'requestAccess').mockResolvedValue({ message: 'ok' })
    const user = userEvent.setup()
    render(<MemoryRouter><RequestAccessPage /></MemoryRouter>)
    await user.type(await screen.findByLabelText('Email'), 'reviewer@example.com')
    await user.click(screen.getByRole('button', { name: 'Request access' }))
    expect(submit).toHaveBeenCalledWith('reviewer@example.com')
    expect(await screen.findByRole('status')).toHaveTextContent(/check your inbox/i)
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })
  it('explains throttling without claiming the request was sent', async () => {
    approval()
    vi.spyOn(api, 'requestAccess').mockRejectedValue(new ApiError(429, 'Too many requests'))
    const user = userEvent.setup()
    render(<MemoryRouter><RequestAccessPage /></MemoryRouter>)
    await user.type(await screen.findByLabelText('Email'), 'reviewer@example.com')
    await user.click(screen.getByRole('button', { name: 'Request access' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/too many requests/i)
  })
  it('keeps registration unavailable without an invitation', async () => {
    approval()
    registrationPage()
    expect(await screen.findByRole('link', { name: /request access/i })).toBeVisible()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })
  it('fixes the invited email and submits the fragment token in the registration body', async () => {
    approval()
    const token = 'a'.repeat(64)
    vi.spyOn(api, 'validateInvitation').mockResolvedValue({ email: 'reviewer@example.com', expires_at: '2026-10-01' })
    const register = vi.spyOn(api, 'register').mockResolvedValue({ id: 'u1', email: 'reviewer@example.com', is_admin: false, created_at: '' })
    const user = userEvent.setup()
    registrationPage(token)
    const email = await screen.findByLabelText('Email')
    expect(email).toHaveValue('reviewer@example.com')
    expect(email).toHaveAttribute('readonly')
    await user.type(screen.getByLabelText('Password'), 'reviewer-password')
    await user.click(screen.getByRole('button', { name: 'Register' }))
    await waitFor(() => expect(register).toHaveBeenCalledWith('reviewer@example.com', 'reviewer-password', token))
    expect(document.body.textContent).not.toContain(token)
  })
  it('rejects expired invitation links without presenting a password form', async () => {
    approval()
    vi.spyOn(api, 'validateInvitation').mockRejectedValue(new ApiError(400, 'Expired'))
    registrationPage('b'.repeat(64))
    expect(await screen.findByRole('alert')).toHaveTextContent(/expired/i)
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })
})

describe('admin requests', () => {
  it('does not fetch requests for a non-administrator', () => {
    const list = vi.spyOn(api, 'accessRequests')
    adminPage(false)
    expect(screen.getByRole('alert')).toHaveTextContent(/administrator access required/i)
    expect(list).not.toHaveBeenCalled()
  })
  it('requires an explicit button press to approve and displays delivery state', async () => {
    vi.spyOn(api, 'accessRequests').mockResolvedValue([pending])
    const approve = vi.spyOn(api, 'approveAccess').mockResolvedValue({ ...pending, status: 'approved' })
    const user = userEvent.setup()
    adminPage()
    await screen.findByText('reviewer@example.com')
    expect(approve).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(approve).toHaveBeenCalledWith('test-token', 'r1')
  })
  it('allows rejecting a request and surfaces API failures', async () => {
    vi.spyOn(api, 'accessRequests').mockResolvedValue([pending])
    const reject = vi.spyOn(api, 'rejectAccess').mockRejectedValue(new ApiError(409, 'Already registered'))
    const user = userEvent.setup()
    adminPage()
    await user.click(await screen.findByRole('button', { name: 'Reject' }))
    expect(reject).toHaveBeenCalledWith('test-token', 'r1')
    expect(await screen.findByRole('alert')).toHaveTextContent('Already registered')
  })
  it('shows a retry action for failed mail delivery', async () => {
    vi.spyOn(api, 'accessRequests').mockResolvedValue([{ ...pending, deliveries: [{ id: 'mail1', kind: 'notification', status: 'failed', attempts: 3, error: 'Email delivery failed', created_at: '', updated_at: '' }] }])
    const retry = vi.spyOn(api, 'retryAccessEmail').mockResolvedValue({ message: 'queued' })
    const user = userEvent.setup()
    adminPage()
    await user.click(await screen.findByRole('button', { name: 'Retry email' }))
    expect(retry).toHaveBeenCalledWith('test-token', 'mail1')
  })
})
