import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { useRegistrationConfig } from '@/hooks/useRegistrationConfig'
import { ApiError } from '@/lib/api'

export function LoginPage() {
  const { login, status } = useAuth()
  const registration = useRegistrationConfig()
  const navigate = useNavigate()
  const location = useLocation()
  const justRegistered = Boolean((location.state as { justRegistered?: boolean } | null)?.justRegistered)
  const destination = (location.state as { from?: string } | null)?.from === '/admin/access-requests' ? '/admin/access-requests' : '/workspace'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to={destination} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate(destination, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? 'Incorrect email or password.'
          : 'Could not reach the server. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>Access your documents and questions.</CardDescription>
        </CardHeader>
        <CardContent>
          {justRegistered && (
            <p role="status" className="mb-4 text-sm text-emerald-600 dark:text-emerald-400">
              Account created. Sign in to continue.
            </p>
          )}
          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
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
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </Button>
            {registration === 'enabled' && <p className="text-center text-sm text-muted-foreground">
              No account?{' '}
              <Link to="/register" className="text-primary underline underline-offset-4">
                Register
              </Link>
            </p>}
            {registration === 'disabled' && (
              <p className="text-center text-sm text-muted-foreground">
                Access is by invitation. Ask the person who shared this demo for an account.
              </p>
            )}
            {registration === 'approval' && <p className="text-center text-sm text-muted-foreground">New here? <Link to="/request-access" className="text-primary underline">Request access</Link></p>}
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
