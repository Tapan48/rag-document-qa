import { useState, type FormEvent } from 'react'

import { AnswerMarkdown } from '@/components/qa/AnswerMarkdown'
import { safeWebUrl } from '@/lib/urls'
import { CitationList } from '@/components/qa/CitationList'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { UseQuestionStreamResult } from '@/hooks/useQuestionStream'
import type { CitationOut } from '@/types/api'

const MAX_QUESTION_LENGTH = 2000

interface QuestionPanelProps {
  webSearch: boolean
  onWebSearchChange: (enabled: boolean) => void
  stream: UseQuestionStreamResult
  canAsk: boolean
  disabledReason: string | null
  onAsk: (question: string) => void
  onSelectCitation: (citation: CitationOut) => void
}

export function QuestionPanel({
  stream,
  webSearch,
  onWebSearchChange,
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
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4">
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="question-input" className="text-sm font-medium">Ask a question</label>
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" role="switch" aria-label="Web search" checked={webSearch}
              onChange={e => onWebSearchChange(e.target.checked)} disabled={isStreaming}
              className="peer sr-only" aria-describedby={webSearch ? 'web-search-help' : undefined} />
            <span aria-hidden="true" className="relative h-6 w-11 rounded-full bg-muted ring-1 ring-border transition-colors after:absolute after:left-1 after:top-1 after:size-4 after:rounded-full after:bg-foreground after:transition-transform peer-checked:bg-primary peer-checked:after:translate-x-5 peer-checked:after:bg-primary-foreground peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-disabled:opacity-50" />
            Web search
          </label>
        </div>
        {webSearch && <p id="web-search-help" className="text-xs text-muted-foreground">
          Search the web alongside your chosen documents. Adds API usage costs.
        </p>}
        <Textarea
          id="question-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, MAX_QUESTION_LENGTH))}
          maxLength={MAX_QUESTION_LENGTH}
          placeholder={webSearch ? "Compare an item with market alternatives, or research a question…" : "What does this document say about…?"}
          rows={3}
          disabled={isStreaming}
          aria-describedby="question-char-count"
        />
        <div className="flex items-center justify-between">
          <span id="question-char-count" className="text-xs text-muted-foreground">
            {draft.length}/{MAX_QUESTION_LENGTH}
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!draft || isStreaming}
              onClick={() => setDraft('')}
            >
              Clear
            </Button>
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

      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-md border border-border p-4" aria-live="polite">
        {stream.phase === 'idle' && !stream.question && (
          <p className="text-sm text-muted-foreground">
            {webSearch ? 'Ask a question to research the web, with any chosen documents as context.' : 'Ask a question about your documents to see a grounded, cited answer here.'}
          </p>
        )}

        {stream.question && (
          <div className="flex flex-col gap-4">
            <p className="text-sm font-medium text-muted-foreground">{stream.question}</p>

            {stream.phase === 'streaming' && (
              <div>
                <p className="whitespace-pre-wrap">{stream.provisionalAnswer}</p>
                <p className="mt-2 text-xs text-muted-foreground" role="status">
                  {stream.statusMessage}
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
                  <AnswerMarkdown answer={stream.finalResponse.answer} citations={stream.finalResponse.citations}
                    webCitations={stream.finalResponse.web_citations} onSelectCitation={onSelectCitation} />
                )}
                {stream.finalResponse.web_search_performed && <p className="text-xs text-muted-foreground">
                  Web research completed. Prices and availability may change.
                </p>}
                <CitationList
                  citations={stream.finalResponse.citations}
                  onSelect={onSelectCitation}
                />
                {!!stream.finalResponse.web_citations?.length && <div className="space-y-2">
                  <p className="text-xs font-medium uppercase text-muted-foreground">Web sources</p>
                  <ul className="space-y-2 text-sm [overflow-wrap:anywhere]">
                    {stream.finalResponse.web_citations.filter(c => safeWebUrl(c.url)).map(c => <li key={c.source_id}>
                      <a className="text-primary underline" href={c.url} target="_blank" rel="noopener noreferrer">[{c.source_id}] {c.title}</a>
                      <span className="block text-xs text-muted-foreground">Researched {new Date(c.researched_at).toLocaleString()}</span>
                    </li>)}
                  </ul>
                </div>}
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
