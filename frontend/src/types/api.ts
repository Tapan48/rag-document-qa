export interface UserPublic {
  id: string
  email: string
  is_admin: boolean
  created_at: string
}

export type RegistrationMode = 'open' | 'approval' | 'closed'
export interface AccessEmailPublic {
  id: string
  kind: 'notification' | 'invitation'
  status: 'pending' | 'retrying' | 'sent' | 'failed' | 'cancelled'
  attempts: number
  error: string | null
  created_at: string
  updated_at: string
}
export interface AccessRequestPublic {
  id: string
  email: string
  status: 'pending' | 'approved' | 'rejected' | 'registered'
  expires_at: string | null
  created_at: string
  deliveries: AccessEmailPublic[]
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
  source_id?: string | null
  chunk_id: string
  document_id: string
  filename: string
  source_metadata: Record<string, unknown>
  text: string
}

export interface WebCitationOut {
  source_id: string
  title: string
  url: string
  researched_at: string
}

export interface QuestionResponse {
  web_citations?: WebCitationOut[]
  web_search_performed?: boolean
  answer: string
  citations: CitationOut[]
  insufficient_evidence: boolean
}

export interface QuestionRequest {
  web_search?: boolean
  question: string
  document_ids?: string[] | null
}

export interface ApiErrorBody {
  detail?: string | { msg: string }[]
}
