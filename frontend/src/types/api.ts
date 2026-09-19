export interface UserPublic {
  id: string
  email: string
  created_at: string
}

export interface Token {
  access_token: string
  token_type: string
}

export type DocumentStatus = 'queued' | 'processing' | 'ready' | 'failed'

export interface DocumentPublic {
  id: string
  filename: string
  status: DocumentStatus
  error_message: string | null
  created_at: string
}

export interface DocumentList {
  items: DocumentPublic[]
  total: number
  limit: number
  offset: number
}

export interface CitationOut {
  chunk_id: string
  document_id: string
  filename: string
  source_metadata: Record<string, unknown>
  text: string
}

export interface QuestionResponse {
  answer: string
  citations: CitationOut[]
  insufficient_evidence: boolean
}

export interface QuestionRequest {
  question: string
  document_ids?: string[] | null
}

export interface ApiErrorBody {
  detail?: string | { msg: string }[]
}
