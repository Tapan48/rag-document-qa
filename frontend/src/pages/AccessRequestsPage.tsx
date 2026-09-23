import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/hooks/useAuth'
import { api, ApiError } from '@/lib/api'
import type { AccessRequestPublic } from '@/types/api'

export function AccessRequestsPage() {
  const { token, user, logout } = useAuth()
  const [requests, setRequests] = useState<AccessRequestPublic[]>([])
  const [offset, setOffset] = useState(0)
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const queryKey = `${offset}:${refresh}`
  const loading = loadedKey !== queryKey
  const handleError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) logout()
    setError(err instanceof ApiError ? err.message : 'Could not reach the server. Try again.')
  }, [logout])
  useEffect(() => {
    if (!token || !user?.is_admin) return
    let cancelled = false
    api.accessRequests(token, offset).then(items => {
      if (!cancelled) { setRequests(items); setError(null) }
    }).catch(err => { if (!cancelled) handleError(err) })
      .finally(() => { if (!cancelled) setLoadedKey(queryKey) })
    return () => { cancelled = true }
  }, [token, user?.is_admin, offset, refresh, queryKey, handleError])
  async function act(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try { await action(); setRefresh(value => value + 1) }
    catch (err) { handleError(err) }
    finally { setBusy(false) }
  }
  if (!user?.is_admin || !token) return <main className="p-6"><p role="alert">Administrator access required.</p><Link to="/workspace">Back to workspace</Link></main>
  return <main className="mx-auto max-w-4xl space-y-5 p-4 sm:p-8">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold">Access requests</h1>
      <Link to="/workspace" className="text-primary underline">Back to workspace</Link>
      <Button variant="outline" disabled={busy || loading} onClick={() => setRefresh(value => value + 1)}>Refresh</Button>
    </header>
    <p className="text-sm text-muted-foreground">Approve a request to email a registration link. Resending replaces the previous link. Refresh to check email delivery.</p>
    {!loading && error && <p role="alert" className="text-destructive">{error}</p>}
    {loading ? <p role="status">Loading requests…</p> : !error && requests.length === 0 && <p>No access requests on this page.</p>}
    {!loading && requests.map(request => <Card key={request.id}>
      <CardHeader><CardTitle className="break-all text-base">{request.email}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p>Status: <strong>{request.status}</strong></p>
        <p className="text-sm text-muted-foreground">Requested {new Date(request.created_at).toLocaleString()}</p>
        {request.expires_at && <p className="text-sm">Invitation expires {new Date(request.expires_at).toLocaleString()}</p>}
        {request.status !== 'registered' && <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => act(() => api.approveAccess(token, request.id))}>{request.status === 'approved' ? 'Resend invitation' : 'Approve'}</Button>
          {request.status !== 'rejected' && <Button variant="outline" disabled={busy} onClick={() => act(() => api.rejectAccess(token, request.id))}>Reject</Button>}
        </div>}
        <ul className="space-y-2 text-sm">{request.deliveries.map(delivery => {
          const stale = Date.now() - Date.parse(delivery.updated_at) >= 5 * 60 * 1000
          const retryable = delivery.status === 'failed' || (stale && ['pending', 'retrying'].includes(delivery.status))
          return <li key={delivery.id} className="rounded border p-2">
            <span>{delivery.kind === 'invitation' ? 'Invitation email' : 'Owner notification'}: {delivery.status} ({delivery.attempts} attempts)</span>
            {delivery.error && <p className="text-destructive">{delivery.error}</p>}
            {retryable && <Button variant="outline" size="sm" className="mt-2" disabled={busy} onClick={() => act(() => api.retryAccessEmail(token, delivery.id))}>Retry email</Button>}
          </li>
        })}</ul>
      </CardContent>
    </Card>)}
    <nav aria-label="Request pages" className="flex gap-3">
      <Button variant="outline" disabled={offset === 0 || busy || loading} onClick={() => setOffset(value => Math.max(0, value - 20))}>Previous</Button>
      <Button variant="outline" disabled={requests.length < 20 || busy || loading} onClick={() => setOffset(value => value + 20)}>Next</Button>
    </nav>
  </main>
}
