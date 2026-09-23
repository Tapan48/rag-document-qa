import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { useRegistrationConfig } from '@/hooks/useRegistrationConfig'
import { ApiError } from '@/lib/api'

export function RegisterPage() {
  const { register, status } = useAuth()
  const registration = useRegistrationConfig()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/workspace" replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setIsSubmitting(true)
    try {
      await register(email, password)
      navigate('/login', { replace: true, state: { justRegistered: true } })
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('Access is by invitation. Ask the person who shared this demo for an account.')
      } else if (err instanceof ApiError && err.status === 409) {
        setError('An account with that email already exists.')
      } else {
        setError('Could not create your account. Please try again.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{registration === 'disabled' ? 'Invite-only access' : 'Create an account'}</CardTitle>
          <CardDescription>
            {registration === 'disabled'
              ? 'Ask the person who shared this demo for an account.'
              : 'Upload documents and ask grounded questions.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {registration === 'loading' && <p role="status">Checking registration availability…</p>}
          {registration === 'error' && <p role="alert">Could not check registration availability. Reload to try again.</p>}
          {registration !== 'enabled' && (
            <Link to="/login" className="text-primary underline underline-offset-4">Sign in</Link>
          )}
          {registration === 'enabled' && <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby="password-hint"
              />
              <p id="password-hint" className="text-xs text-muted-foreground">
                At least 8 characters.
              </p>
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Creating account…' : 'Register'}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Already have an account?{' '}
              <Link to="/login" className="text-primary underline underline-offset-4">
                Sign in
              </Link>
            </p>
          </form>}
        </CardContent>
      </Card>
    </div>
  )
}
