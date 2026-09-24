import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { StatusBadge } from '@/components/documents/StatusBadge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { DocumentPublic } from '@/types/api'

interface DocumentListItemProps {
  document: DocumentPublic
  selectable: boolean
  selected: boolean
  onToggleSelected: (id: string, selected: boolean) => void
  onDelete: (id: string) => Promise<void>
}

export function DocumentListItem({
  document,
  selectable,
  selected,
  onToggleSelected,
  onDelete,
}: DocumentListItemProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const checkboxId = `doc-select-${document.id}`

  async function handleConfirmDelete() {
    setIsDeleting(true)
    try {
      await onDelete(document.id)
      setConfirmOpen(false)
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <li className="flex w-full min-w-0 items-center gap-2 rounded-md border border-border px-3 py-2">
      {selectable && (
        <Checkbox
          id={checkboxId}
          checked={selected}
          onCheckedChange={(checked) => onToggleSelected(document.id, checked === true)}
          aria-label={`Select ${document.filename}`}
        />
      )}
      <label
        htmlFor={selectable ? checkboxId : undefined}
        className="min-w-0 flex-1 cursor-default"
      >
        <p className="truncate text-sm font-medium" title={document.filename}>
          {document.filename}
        </p>
        <div className="mt-1 flex items-center gap-2">
          <StatusBadge status={document.status} />
          {document.status === 'failed' && document.error_message && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-xs text-destructive underline decoration-dotted">
                  why?
                </span>
              </TooltipTrigger>
              <TooltipContent>{document.error_message}</TooltipContent>
            </Tooltip>
          )}
        </div>
      </label>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`Delete ${document.filename}`}>
            <Trash2 className="size-4 text-destructive" />
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete document</DialogTitle>
            <DialogDescription className="[overflow-wrap:anywhere]">
              This permanently deletes “{document.filename}” and everything extracted from it.
              This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={isDeleting}>
              {isDeleting ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  )
}
