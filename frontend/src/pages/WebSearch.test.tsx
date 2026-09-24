import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AnswerMarkdown } from '@/components/qa/AnswerMarkdown'
import { AuthProvider, TOKEN_STORAGE_KEY } from '@/context/AuthContext'
import * as apiModule from '@/lib/api'
import type { StreamCallbacks } from '@/lib/api'
import { WorkspacePage } from '@/pages/WorkspacePage'
import type { WebCitationOut } from '@/types/api'

const WEB: WebCitationOut = { source_id: 'W1', title: 'Manufacturer specs', url: 'https://example.com/spec', researched_at: '2026-09-24T10:00:00Z' }
afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })
async function workspace() {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, 'test-token')
  vi.spyOn(apiModule.api, 'me').mockResolvedValue({ id:'u1', email:'test@example.com', is_admin:false, created_at:'' })
  vi.spyOn(apiModule.api, 'listDocuments').mockResolvedValue({ items:[], total:0, offset:0, limit:20 })
  render(<MemoryRouter><AuthProvider><WorkspacePage /></AuthProvider></MemoryRouter>)
  await screen.findByRole('switch', { name: 'Web search' })
}

it('defaults off, supports web-only questions, locks toggle, and shows research status', async () => {
  let callbacks!: StreamCallbacks
  const spy=vi.spyOn(apiModule,'streamQuestion').mockImplementation(async (_t,_p,c) => { callbacks=c })
  await workspace(); const user=userEvent.setup()
  const toggle=screen.getByRole('switch', {name:'Web search'})
  expect(toggle).not.toBeChecked()
  await user.click(toggle)
  await user.type(screen.getByLabelText('Ask a question'),'Compare power supplies')
  await user.click(screen.getByRole('button',{name:'Ask'}))
  expect(spy.mock.calls[0][1]).toEqual({question:'Compare power supplies',document_ids:null,web_search:true})
  expect(toggle).toBeDisabled()
  expect(screen.getByRole('status')).toHaveTextContent('Searching the web…')
  act(()=>callbacks.onStatus?.('generating'))
  expect(screen.getByRole('status')).toHaveTextContent('Generating answer…')
  act(()=>callbacks.onDone({answer:'A source [W1].',citations:[],web_citations:[WEB],web_search_performed:true,insufficient_evidence:false}))
  expect(await screen.findByRole('link',{name:'[W1]'})).toHaveAttribute('href',WEB.url)
  expect(screen.getByText('Web sources')).toBeInTheDocument()
  expect(toggle).toBeEnabled()
})

it('retains the submitted web mode on retry even after the toggle changes', async () => {
  const spy=vi.spyOn(apiModule,'streamQuestion').mockImplementation(async (_t,_p,c)=>c.onError('web_search_timeout','Web search timed out'))
  await workspace();const user=userEvent.setup()
  await user.click(screen.getByRole('switch',{name:'Web search'}))
  await user.type(screen.getByLabelText('Ask a question'),'Compare items')
  await user.click(screen.getByRole('button',{name:'Ask'}))
  await screen.findByText('Web search timed out')
  await user.click(screen.getByRole('switch',{name:'Web search'}))
  await user.click(screen.getByRole('button',{name:'Retry'}))
  expect(spy).toHaveBeenCalledTimes(2)
  expect(spy.mock.calls[1][1].web_search).toBe(true)
})

it('Stop aborts research and late callbacks cannot replace a newer answer', async () => {
  const callbacks: StreamCallbacks[]=[]
  const signals: AbortSignal[]=[]
  vi.spyOn(apiModule,'streamQuestion').mockImplementation(async (_t,_p,c,s)=>{callbacks.push(c);signals.push(s)})
  await workspace();const user=userEvent.setup()
  await user.click(screen.getByRole('switch',{name:'Web search'}))
  await user.type(screen.getByLabelText('Ask a question'),'Compare')
  await user.click(screen.getByRole('button',{name:'Ask'}))
  await user.click(screen.getByRole('button',{name:'Stop'}))
  expect(signals[0].aborted).toBe(true)
  expect(screen.queryByText('Searching the web…')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'Ask'}))
  act(()=>callbacks[0].onError('late','Old request error'))
  act(()=>callbacks[0].onDone({answer:'Old answer',citations:[],insufficient_evidence:true}))
  expect(screen.queryByText('Old answer')).not.toBeInTheDocument()
  expect(screen.queryByText('Old request error')).not.toBeInTheDocument()
  act(()=>callbacks[1].onDone({answer:'Current answer',citations:[],insufficient_evidence:true}))
  expect(await screen.findByText('Current answer')).toBeInTheDocument()
})

it('Selected documents still requires a selection with web search enabled', async () => {
  await workspace();const user=userEvent.setup()
  await user.click(screen.getByRole('switch',{name:'Web search'}))
  await user.click(screen.getByRole('tab',{name:'Selected documents'}))
  await user.type(screen.getByLabelText('Ask a question'),'Compare')
  expect(screen.getByRole('button',{name:'Ask'})).toBeDisabled()
})

it('renders tables and only verified web URLs, dropping raw HTML and images', () => {
  const {container}=render(<AnswerMarkdown webCitations={[WEB]} answer={
    '| Item | Source |\n| --- | --- |\n| Supply | [W1] |\n\n<script>alert(1)</script>\n\n[bad](javascript:alert) [unknown](https://unverified.example) ![tracking](https://example.com/pixel)'
  } />)
  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getAllByRole('link')).toHaveLength(1)
  expect(screen.getByRole('link')).toHaveAttribute('href',WEB.url)
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img')).toBeNull()
})

it('preserves original document source IDs in inline citations', async () => {
  const citation={source_id:'S3',chunk_id:'c3',document_id:'d1',filename:'spec.txt',text:'24V',source_metadata:{}}
  const select=vi.fn()
  render(<AnswerMarkdown answer="Document [S3]." citations={[citation]} onSelectCitation={select} />)
  await userEvent.click(screen.getByRole('button',{name:'[S3]'}))
  expect(select).toHaveBeenCalledWith(citation)
})
