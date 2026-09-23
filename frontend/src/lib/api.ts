import { parseSseStream } from '@/lib/sse'
import type {
  ApiErrorBody,
  CitationOut,
  DocumentList,
  DocumentPublic,
  QuestionRequest,
  QuestionResponse,
  Token,
  UserPublic,
} from '@/types/api'

const API_BASE = '/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseErrorBody(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail.map((d) => d.msg).join('; ')
    }
  } catch {
    // response body wasn't JSON; fall through to the status text below
  }
  return response.statusText || `Request failed with status ${response.status}`
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  authConfig: () => request<{ registration_enabled: boolean }>('/auth/config'),
  register: (email: string, password: string) =>
    request<UserPublic>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<Token>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: (token: string) => request<UserPublic>('/auth/me', {}, token),

  listDocuments: (token: string, limit = 20, offset = 0) =>
    request<DocumentList>(`/documents?limit=${limit}&offset=${offset}`, {}, token),

  getDocument: (token: string, id: string) =>
    request<DocumentPublic>(`/documents/${id}`, {}, token),

  uploadDocument: (token: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<DocumentPublic>('/documents', { method: 'POST', body: formData }, token)
  },

  deleteDocument: (token: string, id: string) =>
    request<void>(`/documents/${id}`, { method: 'DELETE' }, token),

  askQuestion: (token: string, payload: QuestionRequest) =>
    request<QuestionResponse>(
      '/questions',
      { method: 'POST', body: JSON.stringify(payload) },
      token,
    ),
}

export interface StreamCallbacks {
  onAnswerDelta: (delta: string) => void
  onCitations: (citations: CitationOut[]) => void
  onDone: (response: QuestionResponse) => void
  onError: (code: string, message: string) => void
}

/**
 * Streams POST /questions/stream. Never throws for stream-level problems --
 * every outcome (HTTP error before the stream opens, a mid-stream `error`
 * event, malformed event payloads, or the connection closing without a
 * `done` event) is reported via `callbacks.onError` so the caller doesn't
 * need a try/catch around the whole flow. An aborted request (via `signal`)
 * is treated as neither success nor error -- it resolves silently.
 */
export async function streamQuestion(
  token: string,
  payload: QuestionRequest,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/questions/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    if (signal.aborted || (err as Error).name === 'AbortError') return
    callbacks.onError('network', 'Could not reach the server')
    return
  }

  if (!response.ok) {
    const code = response.status === 401 ? 'unauthorized' : 'http_error'
    callbacks.onError(code, await parseErrorBody(response))
    return
  }
  if (!response.body) {
    callbacks.onError('network', 'Streaming is not supported in this environment')
    return
  }

  let sawDone = false
  try {
    for await (const { event, data } of parseSseStream(response.body)) {
      switch (event) {
        case 'answer': {
          const parsed = JSON.parse(data) as { delta: string }
          callbacks.onAnswerDelta(parsed.delta)
          break
        }
        case 'citations': {
          const parsed = JSON.parse(data) as { citations: CitationOut[] }
          callbacks.onCitations(parsed.citations)
          break
        }
        case 'done': {
          sawDone = true
          callbacks.onDone(JSON.parse(data) as QuestionResponse)
          break
        }
        case 'error': {
          const parsed = JSON.parse(data) as { code: string; message: string }
          callbacks.onError(parsed.code, parsed.message)
          return
        }
        default:
          break
      }
    }
  } catch (err) {
    if (signal.aborted || (err as Error).name === 'AbortError') return
    callbacks.onError('parse_error', 'The answer stream was interrupted')
    return
  }

  if (!sawDone) {
    callbacks.onError('connection_lost', 'Connection closed before the answer finished')
  }
}
