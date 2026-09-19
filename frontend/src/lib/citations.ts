interface TableRef {
  table: number
  row: number
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((v) => typeof v === 'number')
}

function isTableRefArray(value: unknown): value is TableRef[] {
  return (
    Array.isArray(value) &&
    value.every(
      (v) => v && typeof v === 'object' && typeof v.table === 'number' && typeof v.row === 'number',
    )
  )
}

function formatRange(label: string, values: number[]): string {
  if (values.length === 0) return ''
  if (values.length === 1) return `${label} ${values[0]}`
  const min = Math.min(...values)
  const max = Math.max(...values)
  return min === max ? `${label} ${min}` : `${label}s ${min}–${max}`
}

/**
 * Formats a chunk's `source_metadata` into a human-readable reference.
 * PDF pages and TXT line numbers are already 1-based from the backend.
 * DOCX paragraph/table indices are 0-based internally (matching
 * `python-docx`'s own indexing) and are converted to 1-based here for
 * display, since "paragraph 0" would read as a bug to a user.
 */
export function formatSourceMetadata(metadata: Record<string, unknown>): string {
  const parts: string[] = []

  if (isNumberArray(metadata.pages)) {
    const formatted = formatRange('Page', metadata.pages)
    if (formatted) parts.push(formatted)
  }

  if (isNumberArray(metadata.lines)) {
    const formatted = formatRange('Line', metadata.lines)
    if (formatted) parts.push(formatted)
  }

  if (isNumberArray(metadata.paragraphs)) {
    const oneBased = metadata.paragraphs.map((p) => p + 1)
    const formatted = formatRange('Paragraph', oneBased)
    if (formatted) parts.push(formatted)
  }

  if (isTableRefArray(metadata.tables)) {
    const tableParts = metadata.tables.map(
      (ref) => `Table ${ref.table + 1}, Row ${ref.row + 1}`,
    )
    parts.push(...tableParts)
  }

  return parts.length > 0 ? parts.join(' · ') : 'Source location unavailable'
}
