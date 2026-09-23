import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useRegistrationConfig } from '@/hooks/useRegistrationConfig'
import { api, ApiError } from '@/lib/api'

export function RequestAccessPage() {
  const registration = useRegistrationConfig()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.requestAccess(email)
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429
        ? 'Too many requests. Please try again later.'
        : 'Could not submit your request. Please try again.')
    } finally { setBusy(false) }
  }
  return <main className="flex min-h-screen items-center justify-center bg-background px-4">
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Request access</CardTitle>
        <CardDescription>After approval, we’ll email you a link to create your account and choose a password.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {registration === 'loading' && <p role="status">Checking availability…</p>}
        {registration === 'error' && <p role="alert">Could not check availability. Reload to try again.</p>}
        {registration === 'disabled' && <p>Access requests are currently closed.</p>}
        {registration === 'enabled' && <Link className="text-primary underline" to="/register">Create an account</Link>}
        {registration === 'approval' && (sent
          ? <p role="status">If eligible, your request will be reviewed. Check your inbox and spam folder for an invitation after approval.</p>
          : <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy}>{busy ? 'Submitting…' : 'Request access'}</Button>
          </form>)}
        <Link to="/login" className="block text-sm text-primary underline">Already have an account? Sign in</Link>
      </CardContent>
    </Card>
  </main>
}
