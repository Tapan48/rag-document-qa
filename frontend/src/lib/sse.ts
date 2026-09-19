export interface SseEvent {
  event: string
  data: string
}

/**
 * Incrementally parses a Server-Sent Events byte stream into `{event, data}`
 * pairs. Handles three things that a naive line-splitter gets wrong:
 * - network chunk boundaries never aligning with SSE event boundaries
 *   (buffers across reads until a full blank-line-terminated block appears)
 * - multi-byte UTF-8 characters split across chunk boundaries (TextDecoder
 *   in streaming mode, not per-chunk `new TextDecoder().decode(chunk)`)
 * - the SSE spec allowing multiple `data:` lines per event (joined by `\n`)
 */
export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const reader = stream.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const parsed = parseEventBlock(rawEvent)
        if (parsed) yield parsed
        boundary = buffer.indexOf('\n\n')
      }
    }

    buffer += decoder.decode()
    const trailing = parseEventBlock(buffer)
    if (trailing) yield trailing
  } finally {
    reader.releaseLock()
  }
}

function parseEventBlock(block: string): SseEvent | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).replace(/^ /, ''))
    }
  }

  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}
