import type {
  ApiErrorBody,
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
