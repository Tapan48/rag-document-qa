import { useCallback, useEffect, useRef, useState } from 'react'

import { streamQuestion } from '@/lib/api'
import type { QuestionResponse } from '@/types/api'

export type StreamPhase = 'idle' | 'streaming' | 'done' | 'error'

export interface UseQuestionStreamResult {
  phase: StreamPhase
  question: string | null
  provisionalAnswer: string
  finalResponse: QuestionResponse | null
  errorMessage: string | null
  ask: (question: string, documentIds: string[] | null) => void
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
  const [question, setQuestion] = useState<string | null>(null)
  const [provisionalAnswer, setProvisionalAnswer] = useState('')
  const [finalResponse, setFinalResponse] = useState<QuestionResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const lastRequestRef = useRef<{ question: string; documentIds: string[] | null } | null>(null)

  const runStream = useCallback(
    (questionText: string, documentIds: string[] | null) => {
      if (!token) return
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      lastRequestRef.current = { question: questionText, documentIds }

      setQuestion(questionText)
      setProvisionalAnswer('')
      setFinalResponse(null)
      setErrorMessage(null)
      setPhase('streaming')

      void streamQuestion(
        token,
        { question: questionText, document_ids: documentIds },
        {
          onAnswerDelta: (delta) => {
            setProvisionalAnswer((prev) => prev + delta)
          },
          onCitations: () => {
            // Citations also arrive in the authoritative `done` payload; the
            // separate `citations` event exists for early display, which
            // this UI doesn't need since `done` typically follows immediately.
          },
          onDone: (response) => {
            setFinalResponse(response)
            setProvisionalAnswer('')
            setPhase('done')
            abortRef.current = null
          },
          onError: (code, message) => {
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
    (questionText: string, documentIds: string[] | null) => {
      runStream(questionText, documentIds)
    },
    [runStream],
  )

  const retry = useCallback(() => {
    if (!lastRequestRef.current) return
    runStream(lastRequestRef.current.question, lastRequestRef.current.documentIds)
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
    setProvisionalAnswer('')
  }, [])

  return { phase, question, provisionalAnswer, finalResponse, errorMessage, ask, stop, retry }
}
