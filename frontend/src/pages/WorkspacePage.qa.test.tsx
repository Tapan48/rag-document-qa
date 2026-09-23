import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, TOKEN_STORAGE_KEY } from '@/context/AuthContext'
import * as apiModule from '@/lib/api'
import { api } from '@/lib/api'
import type { StreamCallbacks } from '@/lib/api'
import { WorkspacePage } from '@/pages/WorkspacePage'
import type { CitationOut, DocumentPublic, UserPublic } from '@/types/api'

const USER: UserPublic = { id: 'u1', is_admin: false, email: 'a@example.com', created_at: '2026-01-01T00:00:00Z' }
const DOC: DocumentPublic = {
  id: 'd1',
  filename: 'assignment.pdf',
  status: 'ready',
  error_message: null,
  created_at: '2026-01-01T00:00:00Z',
}
const CITATION: CitationOut = {
  chunk_id: 'c1',
  document_id: 'd1',
  filename: 'assignment.pdf',
  source_metadata: { pages: [2] },
  text: 'The time budget is 4-6 hours.',
}

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

async function renderWorkspace() {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, 'token')
  vi.spyOn(api, 'me').mockResolvedValue(USER)
  vi.spyOn(api, 'listDocuments').mockResolvedValue({
    items: [DOC],
    total: 1,
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

describe('WorkspacePage question + citation flow', () => {
  it('shows the provisional answer while streaming, then the final answer with a citation button', async () => {
    vi.spyOn(apiModule, 'streamQuestion').mockImplementation(
      async (_token, _payload, callbacks: StreamCallbacks) => {
        callbacks.onAnswerDelta('The time')
        callbacks.onAnswerDelta(' budget is 4-6 hours.')
        callbacks.onCitations([CITATION])
        callbacks.onDone({
          answer: 'The time budget is 4-6 hours.',
          citations: [CITATION],
          insufficient_evidence: false,
        })
      },
    )
    const user = userEvent.setup()
    await renderWorkspace()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the time budget?')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    await waitFor(() =>
      expect(screen.getByText('The time budget is 4-6 hours.')).toBeInTheDocument(),
    )
    expect(
      screen.getByRole('button', { name: /\[S1\] assignment\.pdf/i }),
    ).toBeInTheDocument()
  })

  it('opens the citation panel with filename, location, and passage text', async () => {
    vi.spyOn(apiModule, 'streamQuestion').mockImplementation(
      async (_token, _payload, callbacks: StreamCallbacks) => {
        callbacks.onDone({
          answer: 'The time budget is 4-6 hours.',
          citations: [CITATION],
          insufficient_evidence: false,
        })
      },
    )
    const user = userEvent.setup()
    await renderWorkspace()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the time budget?')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    const citationButton = await screen.findByRole('button', { name: /\[S1\] assignment\.pdf/i })
    await user.click(citationButton)

    expect(await screen.findByText('Page 2')).toBeInTheDocument()
    expect(screen.getByText('The time budget is 4-6 hours.', { selector: 'pre' })).toBeInTheDocument()
  })

  it('shows an error with a retry action when the stream fails, and discards provisional text', async () => {
    let callCount = 0
    const streamSpy = vi
      .spyOn(apiModule, 'streamQuestion')
      .mockImplementation(async (_token, _payload, callbacks: StreamCallbacks) => {
        callCount += 1
        if (callCount === 1) {
          callbacks.onAnswerDelta('partial text')
          callbacks.onError('timeout', 'Answer generation timed out')
        } else {
          callbacks.onDone({
            answer: 'Recovered answer',
            citations: [],
            insufficient_evidence: true,
          })
        }
      })
    const user = userEvent.setup()
    await renderWorkspace()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the time budget?')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/timed out/i)
    expect(screen.queryByText('partial text')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => expect(screen.getByText('Recovered answer')).toBeInTheDocument())
    expect(streamSpy).toHaveBeenCalledTimes(2)
  })
})
