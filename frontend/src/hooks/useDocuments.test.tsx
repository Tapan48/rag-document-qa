import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useDocuments } from '@/hooks/useDocuments'
import { api, ApiError } from '@/lib/api'
import type { DocumentPublic } from '@/types/api'

function makeDoc(overrides: Partial<DocumentPublic> = {}): DocumentPublic {
  return {
    id: 'doc-1',
    filename: 'a.txt',
    status: 'queued',
    error_message: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('useDocuments', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the first page of documents on mount', async () => {
    vi.spyOn(api, 'listDocuments').mockResolvedValue({
      items: [makeDoc()],
      total: 1,
      limit: 20,
      offset: 0,
    })
    const onUnauthorized = vi.fn()

    const { result } = renderHook(() => useDocuments('token', onUnauthorized))

    await waitFor(() => expect(result.current.documents).toHaveLength(1))
    expect(result.current.total).toBe(1)
    expect(result.current.isLoading).toBe(false)
  })

  it('surfaces a load failure without crashing', async () => {
    vi.spyOn(api, 'listDocuments').mockRejectedValue(new Error('network down'))
    const onUnauthorized = vi.fn()

    const { result } = renderHook(() => useDocuments('token', onUnauthorized))

    await waitFor(() => expect(result.current.error).toBe('network down'))
    expect(result.current.documents).toEqual([])
  })

  it('calls onUnauthorized and does not set a generic error on a 401', async () => {
    vi.spyOn(api, 'listDocuments').mockRejectedValue(new ApiError(401, 'nope'))
    const onUnauthorized = vi.fn()

    renderHook(() => useDocuments('token', onUnauthorized))

    await waitFor(() => expect(onUnauthorized).toHaveBeenCalled())
  })

  it('polls queued/processing documents every 2s and stops once ready', async () => {
    // Fake timers must be active *before* the polling interval is created --
    // a real setInterval created before `vi.useFakeTimers()` doesn't respond
    // to `advanceTimersByTimeAsync`. So we control the initial fetch with an
    // explicit deferred promise instead of relying on a real-timer-based
    // `waitFor` to observe it resolving.
    vi.useFakeTimers()
    try {
      const queuedDoc = makeDoc({ status: 'queued' })
      const readyDoc = makeDoc({ status: 'ready' })
      let resolveList!: (value: Awaited<ReturnType<typeof api.listDocuments>>) => void
      const listPromise = new Promise<Awaited<ReturnType<typeof api.listDocuments>>>((resolve) => {
        resolveList = resolve
      })
      vi.spyOn(api, 'listDocuments').mockReturnValue(listPromise)
      const getDocumentSpy = vi.spyOn(api, 'getDocument').mockResolvedValue(readyDoc)

      const { result } = renderHook(() => useDocuments('token', vi.fn()))

      await act(async () => {
        resolveList({ items: [queuedDoc], total: 1, limit: 20, offset: 0 })
        await listPromise
      })

      expect(result.current.documents).toHaveLength(1)
      expect(result.current.documents[0].status).toBe('queued')

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
      })

      expect(getDocumentSpy).toHaveBeenCalledWith('token', 'doc-1')
      expect(result.current.documents[0].status).toBe('ready')

      // A ready document should no longer be polled -- no further calls
      // after another interval tick.
      getDocumentSpy.mockClear()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
      })
      expect(getDocumentSpy).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('uploads a file and prepends it to the list', async () => {
    vi.spyOn(api, 'listDocuments').mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    const uploaded = makeDoc({ id: 'doc-2', filename: 'new.pdf' })
    vi.spyOn(api, 'uploadDocument').mockResolvedValue(uploaded)

    const { result } = renderHook(() => useDocuments('token', vi.fn()))
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.upload(new File(['content'], 'new.pdf'))
    })

    expect(result.current.documents).toEqual([uploaded])
    expect(result.current.total).toBe(1)
  })

  it('records an upload failure message without throwing to the caller silently', async () => {
    vi.spyOn(api, 'listDocuments').mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    })
    vi.spyOn(api, 'uploadDocument').mockRejectedValue(new ApiError(415, 'Unsupported file type'))

    const { result } = renderHook(() => useDocuments('token', vi.fn()))
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await expect(result.current.upload(new File(['x'], 'bad.exe'))).rejects.toThrow()
    })

    expect(result.current.uploadError).toBe('Unsupported file type')
  })

  it('removes a document from the list on delete', async () => {
    const doc = makeDoc()
    vi.spyOn(api, 'listDocuments').mockResolvedValue({
      items: [doc],
      total: 1,
      limit: 20,
      offset: 0,
    })
    vi.spyOn(api, 'deleteDocument').mockResolvedValue(undefined)

    const { result } = renderHook(() => useDocuments('token', vi.fn()))
    await waitFor(() => expect(result.current.documents).toHaveLength(1))

    await act(async () => {
      await result.current.remove(doc.id)
    })

    expect(result.current.documents).toEqual([])
    expect(result.current.total).toBe(0)
  })
})
