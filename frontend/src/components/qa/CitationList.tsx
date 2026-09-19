import { Button } from '@/components/ui/button'
import type { CitationOut } from '@/types/api'

interface CitationListProps {
  citations: CitationOut[]
  onSelect: (citation: CitationOut) => void
}

export function CitationList({ citations, onSelect }: CitationListProps) {
  if (citations.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Sources</p>
      <div className="flex flex-wrap gap-2">
        {citations.map((citation, index) => (
          <Button
            key={citation.chunk_id}
            variant="outline"
            size="sm"
            onClick={() => onSelect(citation)}
          >
            [S{index + 1}] {citation.filename}
          </Button>
        ))}
      </div>
    </div>
  )
}
