import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { formatSourceMetadata } from '@/lib/citations'
import type { CitationOut } from '@/types/api'

interface CitationPanelProps {
  citation: CitationOut | null
  onOpenChange: (open: boolean) => void
}

export function CitationPanel({ citation, onOpenChange }: CitationPanelProps) {
  return (
    <Sheet open={citation !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        {citation && (
          <>
            <SheetHeader>
              <SheetTitle className="truncate" title={citation.filename}>
                {citation.filename}
              </SheetTitle>
              <SheetDescription>{formatSourceMetadata(citation.source_metadata)}</SheetDescription>
            </SheetHeader>
            <div className="px-4 pb-4">
              <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Supporting passage
              </p>
              <pre className="max-h-[60vh] overflow-y-auto rounded-md bg-muted p-3 text-sm whitespace-pre-wrap">
                {citation.text}
              </pre>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
