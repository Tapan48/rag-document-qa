import { LogOut } from 'lucide-react'
import { useMemo, useState } from 'react'

import { QuestionPanel } from '@/components/qa/QuestionPanel'
import { DocumentSidebar } from '@/components/documents/DocumentSidebar'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useDocuments } from '@/hooks/useDocuments'
import { useQuestionStream } from '@/hooks/useQuestionStream'
import type { SelectionMode } from '@/types/workspace'

export function WorkspacePage() {
  const { user, token, logout } = useAuth()
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('all')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const docs = useDocuments(token, logout)
  const stream = useQuestionStream(token, logout)

  function handleToggleSelected(id: string, selected: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (selected) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const documentIdsForQuestion = useMemo(
    () => (selectionMode === 'selected' ? Array.from(selectedIds) : null),
    [selectionMode, selectedIds],
  )

  const canAsk = selectionMode === 'all' || selectedIds.size > 0
  const disabledReason =
    selectionMode === 'selected' && selectedIds.size === 0
      ? 'Select at least one ready document to ask about it.'
      : null

  function handleAsk(question: string) {
    stream.ask(question, documentIdsForQuestion)
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <h1 className="text-lg font-semibold">Document Q&A</h1>
        <div className="flex items-center gap-3">
          {user && <span className="hidden text-sm text-muted-foreground sm:inline">{user.email}</span>}
          <Button variant="outline" size="sm" onClick={logout}>
            <LogOut className="size-4" /> Log out
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-80 shrink-0 border-r border-border p-4">
          <DocumentSidebar
            docs={docs}
            selectionMode={selectionMode}
            onSelectionModeChange={setSelectionMode}
            selectedIds={selectedIds}
            onToggleSelected={handleToggleSelected}
          />
        </aside>

        <main className="flex-1 overflow-hidden p-4">
          <QuestionPanel
            stream={stream}
            canAsk={canAsk}
            disabledReason={disabledReason}
            onAsk={handleAsk}
          />
        </main>
      </div>
    </div>
  )
}
