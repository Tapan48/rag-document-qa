import { useCallback, useEffect, useRef, useState } from 'react'

import { api, ApiError } from '@/lib/api'
import type { DocumentPublic } from '@/types/api'

const POLL_INTERVAL_MS = 2000
const PAGE_SIZE = 20
const IN_PROGRESS_STATUSES = new Set(['queued', 'processing'])

export interface UseDocumentsResult {
  documents: DocumentPublic[]
  total: number
  isLoading: boolean
  error: string | null
  upload: (file: File) => Promise<void>
  isUploading: boolean
  uploadError: string | null
  remove: (id: string) => Promise<void>
  loadMore: () => void
  hasMore: boolean
}

export function useDocuments(token: string | null, onUnauthorized: () => void): UseDocumentsResult {
  const [documents, setDocuments] = useState<DocumentPublic[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const documentsRef = useRef(documents)
  documentsRef.current = documents

  const handleError = useCallback(
    (err: unknown, setter: (message: string) => void) => {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized()
        return
      }
      setter(err instanceof Error ? err.message : 'Something went wrong')
    },
    [onUnauthorized],
  )

  const fetchPage = useCallback(
    async (pageOffset: number) => {
      if (!token) return
      setIsLoading(true)
      setError(null)
      try {
        const page = await api.listDocuments(token, PAGE_SIZE, pageOffset)
        setDocuments((prev) => (pageOffset === 0 ? page.items : [...prev, ...page.items]))
        setTotal(page.total)
        setOffset(pageOffset)
      } catch (err) {
        handleError(err, setError)
      } finally {
        setIsLoading(false)
      }
    },
    [token, handleError],
  )

  useEffect(() => {
    if (!token) {
      setDocuments([])
      setTotal(0)
      setOffset(0)
      return
    }
    fetchPage(0)
    // Only reload from scratch when the token itself changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // Poll any queued/processing documents every 2s while the tab is visible.
  useEffect(() => {
    if (!token) return
    const inProgressIds = documentsRef.current
      .filter((doc) => IN_PROGRESS_STATUSES.has(doc.status))
      .map((doc) => doc.id)
    if (inProgressIds.length === 0) return

    let cancelled = false
    const interval = window.setInterval(async () => {
      if (cancelled || document.hidden) return
      try {
        const updates = await Promise.all(
          inProgressIds.map((id) => api.getDocument(token, id).catch(() => null)),
        )
        if (cancelled) return
        setDocuments((prev) =>
          prev.map((doc) => {
            const updated = updates.find((u) => u && u.id === doc.id)
            return updated ?? doc
          }),
        )
      } catch {
        // transient poll failure; try again next tick
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
    // Re-arm whenever the set of in-progress documents could have changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, documents])

  const upload = useCallback(
    async (file: File) => {
      if (!token) return
      setIsUploading(true)
      setUploadError(null)
      try {
        const created = await api.uploadDocument(token, file)
        setDocuments((prev) => [created, ...prev])
        setTotal((prev) => prev + 1)
      } catch (err) {
        handleError(err, setUploadError)
        throw err
      } finally {
        setIsUploading(false)
      }
    },
    [token, handleError],
  )

  const remove = useCallback(
    async (id: string) => {
      if (!token) return
      await api.deleteDocument(token, id)
      setDocuments((prev) => prev.filter((doc) => doc.id !== id))
      setTotal((prev) => Math.max(0, prev - 1))
    },
    [token],
  )

  const loadMore = useCallback(() => {
    fetchPage(offset + PAGE_SIZE)
  }, [fetchPage, offset])

  return {
    documents,
    total,
    isLoading,
    error,
    upload,
    isUploading,
    uploadError,
    remove,
    loadMore,
    hasMore: documents.length < total,
  }
}
