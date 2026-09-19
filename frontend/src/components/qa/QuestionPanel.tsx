import { useState, type FormEvent } from 'react'

import { CitationList } from '@/components/qa/CitationList'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { UseQuestionStreamResult } from '@/hooks/useQuestionStream'
import type { CitationOut } from '@/types/api'

const MAX_QUESTION_LENGTH = 2000

interface QuestionPanelProps {
  stream: UseQuestionStreamResult
  canAsk: boolean
  disabledReason: string | null
  onAsk: (question: string) => void
  onSelectCitation: (citation: CitationOut) => void
}

export function QuestionPanel({
  stream,
  canAsk,
  disabledReason,
  onAsk,
  onSelectCitation,
}: QuestionPanelProps) {
  const [draft, setDraft] = useState('')
  const isStreaming = stream.phase === 'streaming'

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed || isStreaming || !canAsk) return
    onAsk(trimmed)
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <label htmlFor="question-input" className="text-sm font-medium">
          Ask a question
        </label>
        <Textarea
          id="question-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, MAX_QUESTION_LENGTH))}
          maxLength={MAX_QUESTION_LENGTH}
          placeholder="What does this document say about…?"
          rows={3}
          disabled={isStreaming}
          aria-describedby="question-char-count"
        />
        <div className="flex items-center justify-between">
          <span id="question-char-count" className="text-xs text-muted-foreground">
            {draft.length}/{MAX_QUESTION_LENGTH}
          </span>
          <div className="flex gap-2">
            {isStreaming ? (
              <Button type="button" variant="outline" onClick={stream.stop}>
                Stop
              </Button>
            ) : (
              <Button type="submit" disabled={!draft.trim() || !canAsk}>
                Ask
              </Button>
            )}
          </div>
        </div>
        {!canAsk && disabledReason && (
          <p className="text-xs text-muted-foreground">{disabledReason}</p>
        )}
      </form>

      <div className="flex-1 overflow-y-auto rounded-md border border-border p-4" aria-live="polite">
        {stream.phase === 'idle' && !stream.question && (
          <p className="text-sm text-muted-foreground">
            Ask a question about your documents to see a grounded, cited answer here.
          </p>
        )}

        {stream.question && (
          <div className="flex flex-col gap-4">
            <p className="text-sm font-medium text-muted-foreground">{stream.question}</p>

            {stream.phase === 'streaming' && (
              <div>
                <p className="whitespace-pre-wrap">{stream.provisionalAnswer}</p>
                <p className="mt-2 text-xs text-muted-foreground" role="status">
                  Generating answer…
                </p>
              </div>
            )}

            {stream.phase === 'done' && stream.finalResponse && (
              <div className="flex flex-col gap-4">
                {stream.finalResponse.insufficient_evidence ? (
                  <Alert>
                    <AlertDescription>{stream.finalResponse.answer}</AlertDescription>
                  </Alert>
                ) : (
                  <p className="whitespace-pre-wrap">{stream.finalResponse.answer}</p>
                )}
                <CitationList
                  citations={stream.finalResponse.citations}
                  onSelect={onSelectCitation}
                />
              </div>
            )}

            {stream.phase === 'error' && (
              <div className="flex flex-col gap-2">
                <Alert variant="destructive">
                  <AlertDescription>{stream.errorMessage}</AlertDescription>
                </Alert>
                <Button variant="outline" size="sm" className="self-start" onClick={stream.retry}>
                  Retry
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
