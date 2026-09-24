import { useCallback, useEffect, useRef, useState } from 'react'

import { streamQuestion } from '@/lib/api'
import type { QuestionResponse } from '@/types/api'

export type StreamPhase = 'idle' | 'streaming' | 'done' | 'error'

export interface UseQuestionStreamResult {
  phase: StreamPhase
  statusMessage: string
  question: string | null
  provisionalAnswer: string
  finalResponse: QuestionResponse | null
  errorMessage: string | null
  ask: (question: string, documentIds: string[] | null, webSearch?: boolean) => void
  stop: () => void
  retry: () => void
}

/**
 * Drives one question at a time against POST /questions/stream. `ask()`
 * cancels any in-flight request first, so only one stream is ever active.
 * `provisionalAnswer` is cleared on both `done` and `error` -- callers must
 * treat it as provisional and only trust `finalResponse` once `phase` is
 * `'done'`.
 */
export function useQuestionStream(
  token: string | null,
  onUnauthorized: () => void,
): UseQuestionStreamResult {
  const [phase, setPhase] = useState<StreamPhase>('idle')
  const [statusMessage, setStatusMessage] = useState('Generating answer…')
  const [question, setQuestion] = useState<string | null>(null)
  const [provisionalAnswer, setProvisionalAnswer] = useState('')
  const [finalResponse, setFinalResponse] = useState<QuestionResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const lastRequestRef = useRef<{ question: string; documentIds: string[] | null; webSearch: boolean } | null>(null)

  const runStream = useCallback(
    (questionText: string, documentIds: string[] | null, webSearch = false) => {
      if (!token) return
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      lastRequestRef.current = { question: questionText, documentIds: documentIds ? [...documentIds] : null, webSearch }

      setQuestion(questionText)
      setProvisionalAnswer('')
      setFinalResponse(null)
      setErrorMessage(null)
      setPhase('streaming')
      setStatusMessage(webSearch ? 'Searching the web…' : 'Generating answer…')

      void streamQuestion(
        token,
        { question: questionText, document_ids: documentIds, web_search: webSearch },
        {
          onStatus: (status) => {
            if (controller.signal.aborted || abortRef.current !== controller) return
            setStatusMessage(status === 'searching' ? 'Searching the web…' : 'Generating answer…')
          },
          onAnswerDelta: (delta) => {
            if (controller.signal.aborted || abortRef.current !== controller) return
            setProvisionalAnswer((prev) => prev + delta)
          },
          onCitations: () => {
            // Citations also arrive in the authoritative `done` payload; the
            // separate `citations` event exists for early display, which
            // this UI doesn't need since `done` typically follows immediately.
          },
          onDone: (response) => {
            if (controller.signal.aborted || abortRef.current !== controller) return
            setFinalResponse(response)
            setProvisionalAnswer('')
            setPhase('done')
            abortRef.current = null
          },
          onError: (code, message) => {
            if (controller.signal.aborted || abortRef.current !== controller) return
            if (code === 'unauthorized') {
              onUnauthorized()
              return
            }
            setProvisionalAnswer('')
            setErrorMessage(message)
            setPhase('error')
            abortRef.current = null
          },
        },
        controller.signal,
      )
    },
    [token, onUnauthorized],
  )

  const ask = useCallback(
    (questionText: string, documentIds: string[] | null, webSearch = false) => {
      runStream(questionText, documentIds, webSearch)
    },
    [runStream],
  )

  const retry = useCallback(() => {
    if (!lastRequestRef.current) return
    runStream(lastRequestRef.current.question, lastRequestRef.current.documentIds, lastRequestRef.current.webSearch)
  }, [runStream])

  // Cancel any in-flight stream if the owning component unmounts -- this is
  // what actually enforces "cancel on logout or navigation" for streaming,
  // since ProtectedRoute unmounts WorkspacePage immediately on logout rather
  // than the component getting a chance to call `stop()` itself.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setPhase('idle')
    setQuestion(null)
    setProvisionalAnswer('')
  }, [])

  return { phase, statusMessage, question, provisionalAnswer, finalResponse, errorMessage, ask, stop, retry }
}
