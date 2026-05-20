/**
 * Render del informe markdown final del agente race-analysis (§10.2 #MarkdownReportViewer).
 *
 * Usa `react-markdown` (ya en deps). El TODO inicial era `remark-gfm`
 * para tablas — NO está instalado, así que se omite (los informes
 * del analyst no incluyen tablas por ahora, sólo listas y secciones).
 *
 * Citas inline tipo `[c1]`, `[1]` quedan visibles tal cual; el
 * tooltip mejorado se difiere a F6.1 cuando exista UI de citations.
 *
 * Privacidad: el markdown ya viene rehidratado por el backend con
 * nombres reales — sólo coach/admin lo ven.
 */
import { useState } from "react";
import { Copy, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { cn } from "@/lib/utils";

interface MarkdownReportViewerProps {
  /** Markdown crudo (raw_markdown del AnalysisOutput). */
  markdown: string;
  /** chunk_ids citados — se renderizan como chips al final si presentes. */
  citations?: string[];
  className?: string;
}

export function MarkdownReportViewer({
  markdown,
  citations = [],
  className,
}: MarkdownReportViewerProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      /* clipboard puede fallar en algunos browsers — silencio. */
    }
  };

  return (
    <article
      className={cn(
        "rounded-xl bg-white p-5 ring-1 ring-light-gray space-y-4",
        className,
      )}
      data-testid="markdown-report-viewer"
    >
      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={handleCopy}
          aria-label="Copiar informe al portapapeles"
          className="inline-flex items-center gap-1.5 rounded-lg border border-light-gray px-3 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-light-gray/40 focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
          data-testid="markdown-copy-button"
        >
          {copied ? (
            <Check size={14} aria-hidden="true" />
          ) : (
            <Copy size={14} aria-hidden="true" />
          )}
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>

      <div className="prose prose-sm max-w-none text-charcoal leading-relaxed">
        <ReactMarkdown
          components={{
            h1: ({ children }) => (
              <h1 className="mt-4 mb-3 text-lg font-semibold text-charcoal first:mt-0">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mt-3 mb-2 text-base font-semibold text-charcoal">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mt-2 mb-2 text-sm font-semibold text-charcoal">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="mb-3 text-sm leading-relaxed last:mb-0">
                {children}
              </p>
            ),
            ul: ({ children }) => (
              <ul className="mb-3 list-disc space-y-1 pl-5 text-sm last:mb-0">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="mb-3 list-decimal space-y-1 pl-5 text-sm last:mb-0">
                {children}
              </ol>
            ),
            li: ({ children }) => <li>{children}</li>,
            strong: ({ children }) => (
              <strong className="font-semibold text-charcoal">{children}</strong>
            ),
            em: ({ children }) => <em className="italic">{children}</em>,
            code: ({ children }) => (
              <code className="rounded bg-light-gray px-1 py-0.5 text-xs">
                {children}
              </code>
            ),
            blockquote: ({ children }) => (
              <blockquote className="mb-3 border-l-4 border-light-gray pl-4 italic text-mid-gray">
                {children}
              </blockquote>
            ),
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline hover:text-blue-800"
              >
                {children}
              </a>
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>

      {citations.length > 0 && (
        <div
          className="border-t border-light-gray pt-3"
          aria-label="Citas referenciadas"
        >
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mid-gray">
            Citas
          </p>
          <ul className="flex flex-wrap gap-1.5" data-testid="markdown-citations">
            {citations.map((c) => (
              <li
                key={c}
                className="rounded-full bg-light-gray px-2.5 py-1 text-xs font-medium text-charcoal"
                title={`Chunk ${c} del marco teórico`}
              >
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
