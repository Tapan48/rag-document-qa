import { describe, expect, it } from 'vitest'

import { parseSseStream } from '@/lib/sse'

function streamFromChunks(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  let index = 0
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(chunks[index])
        index += 1
      } else {
        controller.close()
      }
    },
  })
}

function encode(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = []
  for await (const event of parseSseStream(stream)) {
    events.push(event)
  }
  return events
}

describe('parseSseStream', () => {
  it('parses a single complete event in one chunk', async () => {
    const stream = streamFromChunks([encode('event: answer\ndata: {"delta":"hi"}\n\n')])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'answer', data: '{"delta":"hi"}' }])
  })

  it('parses multiple events delivered in one chunk', async () => {
    const stream = streamFromChunks([
      encode('event: answer\ndata: {"delta":"a"}\n\nevent: answer\ndata: {"delta":"b"}\n\n'),
    ])

    const events = await collect(stream)

    expect(events).toEqual([
      { event: 'answer', data: '{"delta":"a"}' },
      { event: 'answer', data: '{"delta":"b"}' },
    ])
  })

  it('reassembles an event split across multiple network chunks', async () => {
    const full = 'event: answer\ndata: {"delta":"hello"}\n\n'
    const stream = streamFromChunks([
      encode(full.slice(0, 10)),
      encode(full.slice(10, 25)),
      encode(full.slice(25)),
    ])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'answer', data: '{"delta":"hello"}' }])
  })

  it('reassembles a multi-byte UTF-8 character split across a chunk boundary', async () => {
    // "é" is 2 bytes in UTF-8 (0xC3 0xA9); split right between them.
    const payload = 'event: answer\ndata: {"delta":"café"}\n\n'
    const bytes = encode(payload)
    const splitIndex = payload.indexOf('caf') + 3 + 1 // right after the first byte of "é"

    const stream = streamFromChunks([bytes.slice(0, splitIndex), bytes.slice(splitIndex)])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'answer', data: '{"delta":"café"}' }])
  })

  it('joins multiple data lines within one event per the SSE spec', async () => {
    const stream = streamFromChunks([encode('event: answer\ndata: line1\ndata: line2\n\n')])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'answer', data: 'line1\nline2' }])
  })

  it('defaults to event type "message" when no event: line is present', async () => {
    const stream = streamFromChunks([encode('data: hello\n\n')])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'message', data: 'hello' }])
  })

  it('ignores a block with no data line', async () => {
    const stream = streamFromChunks([encode(': this is a comment\n\ndata: real\n\n')])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'message', data: 'real' }])
  })

  it('parses a trailing event with no final blank line', async () => {
    const stream = streamFromChunks([encode('event: done\ndata: {"ok":true}')])

    const events = await collect(stream)

    expect(events).toEqual([{ event: 'done', data: '{"ok":true}' }])
  })

  it('parses a realistic multi-event sequence matching the backend format', async () => {
    const backendOutput =
      'event: answer\ndata: {"delta": "The"}\n\n' +
      'event: answer\ndata: {"delta": " sky"}\n\n' +
      'event: citations\ndata: {"citations": []}\n\n' +
      'event: done\ndata: {"answer": "The sky", "citations": [], "insufficient_evidence": false}\n\n'

    const stream = streamFromChunks([encode(backendOutput)])

    const events = await collect(stream)

    expect(events.map((e) => e.event)).toEqual(['answer', 'answer', 'citations', 'done'])
  })
})
