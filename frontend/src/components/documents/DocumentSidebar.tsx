import { Loader2, Upload } from 'lucide-react'
import { useRef, type ChangeEvent } from 'react'

import { DocumentListItem } from '@/components/documents/DocumentListItem'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { UseDocumentsResult } from '@/hooks/useDocuments'
import type { SelectionMode } from '@/types/workspace'

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt']

interface DocumentSidebarProps {
  docs: UseDocumentsResult
  selectionMode: SelectionMode
  onSelectionModeChange: (mode: SelectionMode) => void
  selectedIds: Set<string>
  onToggleSelected: (id: string, selected: boolean) => void
}

export function DocumentSidebar({
  docs,
  selectionMode,
  onSelectionModeChange,
  selectedIds,
  onToggleSelected,
}: DocumentSidebarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    // The backend is the source of truth for type/size validation (415/413);
    // we just attempt the upload and let `docs.uploadError` surface whatever
    // it reports, rather than duplicating that logic here and risking drift.
    docs.upload(file).catch(() => {
      /* surfaced via docs.uploadError */
    })
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={handleFileChosen}
          aria-label="Upload document"
        />
        <Button
          className="w-full"
          onClick={() => fileInputRef.current?.click()}
          disabled={docs.isUploading}
        >
          {docs.isUploading ? (
            <>
              <Loader2 className="size-4 animate-spin" /> Uploading…
            </>
          ) : (
            <>
              <Upload className="size-4" /> Upload document
            </>
          )}
        </Button>
        <p className="mt-1 text-xs text-muted-foreground">PDF, DOCX, or TXT — up to 20MB.</p>
        {docs.uploadError && (
          <Alert variant="destructive" className="mt-2">
            <AlertDescription>{docs.uploadError}</AlertDescription>
          </Alert>
        )}
      </div>

      <Tabs value={selectionMode} onValueChange={(v) => onSelectionModeChange(v as SelectionMode)}>
        <TabsList className="w-full">
          <TabsTrigger value="all" className="flex-1">
            All ready documents
          </TabsTrigger>
          <TabsTrigger value="selected" className="flex-1">
            Selected documents
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <ScrollArea className="flex-1">
        {docs.isLoading && docs.documents.length === 0 ? (
          <div className="flex flex-col gap-2" aria-hidden="true">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : docs.error ? (
          <Alert variant="destructive">
            <AlertDescription>{docs.error}</AlertDescription>
          </Alert>
        ) : docs.documents.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No documents yet. Upload one to get started.
          </p>
        ) : (
          <ul className="flex flex-col gap-2" aria-label="Your documents">
            {docs.documents.map((doc) => (
              <DocumentListItem
                key={doc.id}
                document={doc}
                selectable={selectionMode === 'selected' && doc.status === 'ready'}
                selected={selectedIds.has(doc.id)}
                onToggleSelected={onToggleSelected}
                onDelete={docs.remove}
              />
            ))}
          </ul>
        )}
        {docs.hasMore && !docs.isLoading && (
          <Button variant="ghost" className="mt-2 w-full" onClick={docs.loadMore}>
            Load more
          </Button>
        )}
      </ScrollArea>
    </div>
  )
}
