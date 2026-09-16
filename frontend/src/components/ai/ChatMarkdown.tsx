/**
 * ChatMarkdown — render compacto de Markdown (con tablas GFM) para burbujas
 * de chat de IA (CompetitionChatPanel / AthleteAnalystChatPanel).
 *
 * Hermano más denso de MarkdownReportViewer (§10.2): mismo `react-markdown`,
 * pero sin el wrapper "article" ni el botón de copiar, y con `remark-gfm`
 * para las tablas que el asistente arma en respuestas ad-hoc.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatMarkdownProps {
  content: string;
}

export function ChatMarkdown({ content }: ChatMarkdownProps) {
  return (
    <div className="prose prose-sm max-w-none text-inherit leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="mb-2 last:mb-0">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="mb-2 list-disc space-y-0.5 pl-4 last:mb-0">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 list-decimal space-y-0.5 pl-4 last:mb-0">
              {children}
            </ol>
          ),
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ children }) => (
            <code className="rounded bg-black/10 px-1 py-0.5 text-xs">
              {children}
            </code>
          ),
          blockquote: ({ children }) => (
            <blockquote className="mb-2 border-l-2 border-current/30 pl-3 italic last:mb-0">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="mb-2 overflow-x-auto last:mb-0">
              <table className="min-w-full border-collapse text-xs">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b border-current/20">{children}</thead>
          ),
          tr: ({ children }) => (
            <tr className="border-b border-current/10 last:border-0">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="px-2 py-1">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
