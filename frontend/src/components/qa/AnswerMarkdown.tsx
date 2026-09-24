import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Root, RootContent, Text } from 'mdast'

import { safeWebUrl } from '@/lib/urls'
import type { CitationOut, WebCitationOut } from '@/types/api'

// Convert source markers in ordinary Markdown text, never in code or existing links.
function sourceMarkers() {
  return (tree: Root) => {
    function walk(node: Root | RootContent) {
      if (!('children' in node) || ['link', 'linkReference', 'code', 'inlineCode'].includes(node.type)) return
      const children: RootContent[] = []
      for (const child of node.children) {
        if (child.type !== 'text') { walk(child); children.push(child); continue }
        let offset = 0
        for (const match of child.value.matchAll(/\[([SW]\d+)\]/g)) {
          if (match.index > offset) children.push({ type: 'text', value: child.value.slice(offset, match.index) })
          children.push({ type: 'link', url: `#source-${match[1]}`, children: [{ type: 'text', value: match[0] }] })
          offset = match.index + match[0].length
        }
        if (offset < child.value.length) children.push({ type: 'text', value: child.value.slice(offset) } as Text)
      }
      // The traversal only replaces text nodes with valid inline phrasing nodes.
      node.children = children as typeof node.children
    }
    walk(tree)
  }
}

interface Props {
  answer: string
  citations?: CitationOut[]
  webCitations?: WebCitationOut[]
  onSelectCitation?: (citation: CitationOut) => void
}

export function AnswerMarkdown({ answer, citations = [], webCitations = [], onSelectCitation }: Props) {
  const webById = new Map(webCitations.filter(c => safeWebUrl(c.url)).map(c => [c.source_id, c]))
  const docById = new Map(citations.map((c, i) => [c.source_id ?? `S${i + 1}`, c]))
  const allowedUrls = new Set([...webById.values()].map(c => c.url))
  return (
    <div className="min-w-0 space-y-3 text-sm leading-relaxed [overflow-wrap:anywhere]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, sourceMarkers]}
        skipHtml
        urlTransform={url => /^#source-[SW]\d+$/.test(url) || (safeWebUrl(url) && allowedUrls.has(url)) ? url : ''}
        components={{
          a: ({ href, children }) => {
            const id = href?.startsWith('#source-') ? href.slice(8) : ''
            const doc = docById.get(id)
            if (doc && onSelectCitation) return <button className="text-primary underline" onClick={() => onSelectCitation(doc)}>{children}</button>
            const url = webById.get(id)?.url ?? href
            if (!url || !safeWebUrl(url) || !allowedUrls.has(url)) return <span>{children}</span>
            return <a href={url} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a>
          },
          img: () => null,
          table: ({ children }) => <div className="max-w-full overflow-x-auto"><table className="w-full border-collapse text-left">{children}</table></div>,
          th: ({ children }) => <th className="min-w-36 [overflow-wrap:normal] border border-border bg-muted px-3 py-2 align-top font-semibold">{children}</th>,
          td: ({ children }) => <td className="border border-border px-3 py-2 align-top">{children}</td>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
          pre: ({ children }) => <pre className="overflow-x-auto rounded bg-muted p-3">{children}</pre>,
        }}
      >{answer}</ReactMarkdown>
    </div>
  )
}
