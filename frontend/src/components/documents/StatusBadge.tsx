import { Badge } from '@/components/ui/badge'
import type { DocumentStatus } from '@/types/api'

const LABELS: Record<DocumentStatus, string> = {
  queued: 'Queued',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

const VARIANT_CLASSES: Record<DocumentStatus, string> = {
  queued: 'bg-muted text-muted-foreground',
  processing: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  ready: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  failed: 'bg-destructive/15 text-destructive',
}

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <Badge variant="outline" className={VARIANT_CLASSES[status]}>
      {LABELS[status]}
    </Badge>
  )
}
