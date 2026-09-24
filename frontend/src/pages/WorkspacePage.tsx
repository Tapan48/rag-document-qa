import { LogOut, PanelLeft } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { CitationPanel } from '@/components/qa/CitationPanel'
import { QuestionPanel } from '@/components/qa/QuestionPanel'
import { DocumentSidebar } from '@/components/documents/DocumentSidebar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { useAuth } from '@/hooks/useAuth'
import { useDocuments } from '@/hooks/useDocuments'
import { useQuestionStream } from '@/hooks/useQuestionStream'
import type { CitationOut } from '@/types/api'
import type { SelectionMode } from '@/types/workspace'

export function WorkspacePage() {
  const { user, token, logout } = useAuth()
  const [webSearch, setWebSearch] = useState(false)
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('all')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [activeCitation, setActiveCitation] = useState<CitationOut | null>(null)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  const handleUnauthorized = useCallback(() => {
    logout()
  }, [logout])

  const docs = useDocuments(token, handleUnauthorized)
  const stream = useQuestionStream(token, handleUnauthorized)

  function handleToggleSelected(id: string, selected: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (selected) next.add(id)
      else next.delete(id)
      return next
    })
  }

  function handleLogout() {
    logout()
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
    stream.ask(question, documentIdsForQuestion, webSearch)
  }

  const sidebar = (
    <DocumentSidebar
      docs={docs}
      selectionMode={selectionMode}
      onSelectionModeChange={setSelectionMode}
      selectedIds={selectedIds}
      onToggleSelected={handleToggleSelected}
    />
  )

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open document list"
            onClick={() => setMobileSidebarOpen(true)}
          >
            <PanelLeft className="size-5" />
          </Button>
          <h1 className="text-lg font-semibold">Document Q&A</h1>
        </div>
        <div className="flex items-center gap-3">
          {user?.is_admin && <Link to="/admin/access-requests" className="text-sm text-primary underline">Access requests</Link>}
          {user && <span className="hidden text-sm text-muted-foreground sm:inline">{user.email}</span>}
          <Button variant="outline" size="sm" onClick={handleLogout}>
            <LogOut className="size-4" /> Log out
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="hidden w-80 shrink-0 border-r border-border p-4 md:block">{sidebar}</aside>

        <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
          <SheetContent side="left" className="w-80 p-4">
            <SheetTitle className="sr-only">Documents</SheetTitle>
            {sidebar}
          </SheetContent>
        </Sheet>

        <main className="min-w-0 flex-1 overflow-hidden p-4">
          <QuestionPanel
            stream={stream}
            webSearch={webSearch}
            onWebSearchChange={setWebSearch}
            canAsk={canAsk}
            disabledReason={disabledReason}
            onAsk={handleAsk}
            onSelectCitation={setActiveCitation}
          />
        </main>
      </div>

      <CitationPanel citation={activeCitation} onOpenChange={(open) => !open && setActiveCitation(null)} />
    </div>
  )
}
