import { describe, expect, it } from 'vitest'

import { formatSourceMetadata } from '@/lib/citations'

describe('formatSourceMetadata', () => {
  it('formats a single page', () => {
    expect(formatSourceMetadata({ pages: [1] })).toBe('Page 1')
  })

  it('formats a page range', () => {
    expect(formatSourceMetadata({ pages: [3, 4, 5] })).toBe('Pages 3–5')
  })

  it('formats a single line', () => {
    expect(formatSourceMetadata({ lines: [10] })).toBe('Line 10')
  })

  it('formats a line range', () => {
    expect(formatSourceMetadata({ lines: [1, 4] })).toBe('Lines 1–4')
  })

  it('converts 0-based DOCX paragraph indices to 1-based for display', () => {
    expect(formatSourceMetadata({ paragraphs: [0] })).toBe('Paragraph 1')
    expect(formatSourceMetadata({ paragraphs: [0, 1, 2] })).toBe('Paragraphs 1–3')
  })

  it('converts 0-based DOCX table/row indices to 1-based for display', () => {
    expect(formatSourceMetadata({ tables: [{ table: 0, row: 0 }] })).toBe('Table 1, Row 1')
  })

  it('combines paragraphs and tables when both are present', () => {
    expect(
      formatSourceMetadata({ paragraphs: [0], tables: [{ table: 0, row: 1 }] }),
    ).toBe('Paragraph 1 · Table 1, Row 2')
  })

  it('falls back to a placeholder when no known keys are present', () => {
    expect(formatSourceMetadata({})).toBe('Source location unavailable')
  })
})
