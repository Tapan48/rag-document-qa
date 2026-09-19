import { afterEach, describe, expect, it, vi } from 'vitest'

import { streamQuestion } from '@/lib/api'
import type { CitationOut } from '@/types/api'

function sseStreamFromEvents(blocks: string[]): ReadableStream<Uint8Array<ArrayBuffer>> {
  const encoder = new TextEncoder()
  let index = 0
  return new ReadableStream<Uint8Array<ArrayBuffer>>({
    pull(controller) {
      if (index < blocks.length) {
        controller.enqueue(encoder.encode(blocks[index]))
        index += 1
      } else {
        controller.close()
      }
    },
  })
}

function mockFetchResponse(response: Partial<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(response as Response),
  )
}

function callbackSpies() {
  return {
    onAnswerDelta: vi.fn(),
    onCitations: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('streamQuestion', () => {
  it('delivers deltas, citations, and done in order on success', async () => {
    const body = sseStreamFromEvents([
      'event: answer\ndata: {"delta":"hel"}\n\n',
      'event: answer\ndata: {"delta":"lo"}\n\n',
      'event: citations\ndata: {"citations":[]}\n\n',
      'event: done\ndata: {"answer":"hello","citations":[],"insufficient_evidence":false}\n\n',
    ])
    mockFetchResponse({ ok: true, status: 200, body })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onAnswerDelta.mock.calls).toEqual([['hel'], ['lo']])
    expect(callbacks.onCitations).toHaveBeenCalledWith([])
    expect(callbacks.onDone).toHaveBeenCalledWith({
      answer: 'hello',
      citations: [],
      insufficient_evidence: false,
    })
    expect(callbacks.onError).not.toHaveBeenCalled()
  })

  it('reports an ordinary HTTP error before the stream opens', async () => {
    mockFetchResponse({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({ detail: 'Document is not ready' }),
    })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onError).toHaveBeenCalledWith('http_error', 'Document is not ready')
    expect(callbacks.onDone).not.toHaveBeenCalled()
  })

  it('reports a distinct "unauthorized" code for a 401 before the stream opens', async () => {
    mockFetchResponse({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Could not validate credentials' }),
    })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onError).toHaveBeenCalledWith('unauthorized', 'Could not validate credentials')
  })

  it('reports a mid-stream error event and stops before done', async () => {
    const body = sseStreamFromEvents([
      'event: answer\ndata: {"delta":"partial"}\n\n',
      'event: error\ndata: {"code":"timeout","message":"Answer generation timed out"}\n\n',
    ])
    mockFetchResponse({ ok: true, status: 200, body })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onError).toHaveBeenCalledWith('timeout', 'Answer generation timed out')
    expect(callbacks.onDone).not.toHaveBeenCalled()
  })

  it('reports connection_lost when the stream ends without a done event', async () => {
    const body = sseStreamFromEvents(['event: answer\ndata: {"delta":"partial"}\n\n'])
    mockFetchResponse({ ok: true, status: 200, body })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onError).toHaveBeenCalledWith(
      'connection_lost',
      expect.stringContaining('before the answer finished'),
    )
    expect(callbacks.onDone).not.toHaveBeenCalled()
  })

  it('reports parse_error on malformed event JSON instead of throwing', async () => {
    const body = sseStreamFromEvents(['event: answer\ndata: {not valid json\n\n'])
    mockFetchResponse({ ok: true, status: 200, body })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onError).toHaveBeenCalledWith('parse_error', expect.any(String))
  })

  it('silently resolves on client-initiated abort without calling onError', async () => {
    const controller = new AbortController()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => {
        controller.abort()
        const err = new Error('aborted')
        err.name = 'AbortError'
        return Promise.reject(err)
      }),
    )
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, controller.signal)

    expect(callbacks.onError).not.toHaveBeenCalled()
    expect(callbacks.onDone).not.toHaveBeenCalled()
  })

  it('passes citations through with full shape intact', async () => {
    const citation: CitationOut = {
      chunk_id: 'c1',
      document_id: 'd1',
      filename: 'doc.pdf',
      source_metadata: { pages: [1] },
      text: 'some passage',
    }
    const body = sseStreamFromEvents([
      `event: citations\ndata: {"citations":[${JSON.stringify(citation)}]}\n\n`,
      'event: done\ndata: {"answer":"a","citations":[],"insufficient_evidence":false}\n\n',
    ])
    mockFetchResponse({ ok: true, status: 200, body })
    const callbacks = callbackSpies()

    await streamQuestion('token', { question: 'q' }, callbacks, new AbortController().signal)

    expect(callbacks.onCitations).toHaveBeenCalledWith([citation])
  })
})
