import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { useRegistrationConfig } from '@/hooks/useRegistrationConfig'
import { api, ApiError } from '@/lib/api'

export function RegisterPage() {
  const { register, status } = useAuth()
  const registration = useRegistrationConfig()
  const navigate = useNavigate()
  const location = useLocation()
  const invitationToken = new URLSearchParams(location.hash.slice(1)).get('token') ?? ''
  const [invitation, setInvitation] = useState<{ token: string; email: string } | null>(null)
  const [invitationError, setInvitationError] = useState<{ token: string; message: string } | null>(null)
  const invitationMessage = invitationError?.token === invitationToken ? invitationError.message : null
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  useEffect(() => {
    if (registration !== 'approval' || !invitationToken) return
    let cancelled = false
    api.validateInvitation(invitationToken).then(value => {
      if (!cancelled) setInvitation({ token: invitationToken, email: value.email })
    }).catch(err => {
      if (!cancelled) setInvitationError({ token: invitationToken, message: err instanceof ApiError && err.status === 400
        ? 'This invitation is invalid, expired, or already used. Ask for a new invitation.'
        : 'Could not check your invitation. Reload to try again.' })
    })
    return () => { cancelled = true }
  }, [registration, invitationToken])
  if (status === 'authenticated') return <Navigate to="/workspace" replace />
  const invited = registration === 'approval' && invitation?.token === invitationToken
  const canRegister = registration === 'enabled' || invited
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!canRegister) return
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    setIsSubmitting(true)
    try {
      await register(invited ? invitation.email : email, password, invited ? invitationToken : undefined)
      navigate('/login', { replace: true, state: { justRegistered: true } })
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setError('Access is by invitation. Request access before registering.')
      else if (err instanceof ApiError && err.status === 409) setError('An account with that email already exists. Sign in instead.')
      else if (err instanceof ApiError && err.status === 400) setError('This invitation is no longer valid. Ask for a new invitation.')
      else setError('Could not create your account. Please try again.')
    } finally { setIsSubmitting(false) }
  }
  return <main className="flex min-h-screen items-center justify-center bg-background px-4">
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>{registration === 'disabled' || (registration === 'approval' && !invitationToken) ? 'Invite-only access' : 'Create an account'}</CardTitle>
        <CardDescription>{registration === 'approval' ? 'Use your emailed invitation to choose your own password.' : registration === 'disabled' ? 'Ask the person who shared this demo for an account.' : 'Upload documents and ask grounded questions.'}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {registration === 'loading' && <p role="status">Checking registration availability…</p>}
        {registration === 'error' && <p role="alert">Could not check registration availability. Reload to try again.</p>}
        {registration === 'approval' && !canRegister && <>
          {invitationToken && !invitationMessage && <p role="status">Checking invitation…</p>}
          {invitationMessage && <p role="alert">{invitationMessage}</p>}
          <Link to="/request-access" className="block text-primary underline">Request access</Link>
        </>}
        {canRegister && <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" required readOnly={invited} value={invited ? invitation.email : email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)} aria-describedby="password-hint" />
            <p id="password-hint" className="text-xs text-muted-foreground">At least 8 characters.</p>
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Creating account…' : 'Register'}</Button>
        </form>}
        <Link to="/login" className="block text-sm text-primary underline">Sign in</Link>
      </CardContent>
    </Card>
  </main>
}
