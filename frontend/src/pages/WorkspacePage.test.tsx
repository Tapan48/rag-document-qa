import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, TOKEN_STORAGE_KEY } from '@/context/AuthContext'
import { api } from '@/lib/api'
import { WorkspacePage } from '@/pages/WorkspacePage'
import type { DocumentPublic, UserPublic } from '@/types/api'

const USER: UserPublic = { id: 'u1', is_admin: false, email: 'a@example.com', created_at: '2026-01-01T00:00:00Z' }

function readyDoc(id: string, filename: string): DocumentPublic {
  return { id, filename, status: 'ready', error_message: null, created_at: '2026-01-01T00:00:00Z' }
}

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

async function renderWorkspace(documents: DocumentPublic[]) {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, 'token')
  vi.spyOn(api, 'me').mockResolvedValue(USER)
  vi.spyOn(api, 'listDocuments').mockResolvedValue({
    items: documents,
    total: documents.length,
    limit: 20,
    offset: 0,
  })

  render(
    <MemoryRouter initialEntries={['/workspace']}>
      <AuthProvider>
        <WorkspacePage />
      </AuthProvider>
    </MemoryRouter>,
  )

  await waitFor(() => expect(screen.getByRole('button', { name: /ask/i })).toBeInTheDocument())
}

describe('WorkspacePage selection modes', () => {
  it('allows asking in "All ready documents" mode with no selection required', async () => {
    await renderWorkspace([readyDoc('d1', 'a.pdf')])
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is this about?')

    expect(screen.getByRole('button', { name: /ask/i })).toBeEnabled()
  })

  it('disables Ask in "Selected documents" mode until a document is checked', async () => {
    await renderWorkspace([readyDoc('d1', 'a.pdf')])
    const user = userEvent.setup()

    await user.click(screen.getByRole('tab', { name: /selected documents/i }))
    await user.type(screen.getByLabelText(/ask a question/i), 'What is this about?')

    expect(screen.getByRole('button', { name: /ask/i })).toBeDisabled()
    expect(screen.getByText(/select at least one ready document/i)).toBeInTheDocument()

    await user.click(screen.getByLabelText(/select a\.pdf/i))

    expect(screen.getByRole('button', { name: /ask/i })).toBeEnabled()
  })

  it('does not offer a checkbox for a non-ready document in "Selected documents" mode', async () => {
    const processingDoc: DocumentPublic = {
      id: 'd2',
      filename: 'b.pdf',
      status: 'processing',
      error_message: null,
      created_at: '2026-01-01T00:00:00Z',
    }
    await renderWorkspace([processingDoc])
    const user = userEvent.setup()

    await user.click(screen.getByRole('tab', { name: /selected documents/i }))

    expect(screen.queryByLabelText(/select b\.pdf/i)).not.toBeInTheDocument()
  })
})
