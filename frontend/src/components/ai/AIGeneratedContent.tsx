import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { PHVBadge } from "@/components/athletes/PHVBadge";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import type { PHVExplanationResponse } from "@/types/ai.types";
import { MaturationStatus, UserRole } from "@/types/enums";

interface AIGeneratedContentProps {
  data: PHVExplanationResponse;
  className?: string;
}

function statusOrNull(value: string): MaturationStatus | null {
  if (
    value === MaturationStatus.PrePHV ||
    value === MaturationStatus.CircaPHV ||
    value === MaturationStatus.PostPHV
  ) {
    return value;
  }
  return null;
}

/** Contenedor reutilizable para texto generado por IA.
 *
 * Renderiza: badge PHV, procedencia, fecha de generación, disclaimer
 * obligatorio, texto y botón "Copiar". El disclaimer NO es ocultable
 * (responsabilidad del componente, no del consumidor).
 *
 * Procedencia por audiencia (FR-029): toda persona ve la línea fija
 * "Generado por el asistente de IA del club" con la fecha, nunca el
 * proveedor ni el modelo. Solo un coach/admin (según el rol de la sesión
 * actual, `useAuthStore` — el mismo gating por rol que
 * `GrowthCurveSection`/`PercentileCurves`) obtiene además un disclosure
 * real `<details>/<summary>` (accesible por teclado de forma nativa) con
 * el modelo, la versión del prompt y la referencia de traza. Se decide por
 * el ROL de quien mira, no por el `audience` de contenido pedido al
 * backend (measurement-analysis-api.md §4: un coach previsualizando el
 * texto en modo familia sigue siendo el humano en el ciclo y nunca debe
 * quedar ciego a la procedencia técnica). Una familia jamás llega a este
 * bloque: no se oculta con CSS, no se renderiza.
 *
 * Privacidad:
 *  - Nunca pasamos `data.text` a `title`, `aria-label` o `data-*` para
 *    evitar exposición vía DOM inspeccionable.
 *  - El componente solo lee campos de la allowlist; cualquier campo extra
 *    en `data` queda invisible.
 */
export function AIGeneratedContent({
  data,
  className,
}: AIGeneratedContentProps) {
  const [copied, setCopied] = useState(false);
  const status = statusOrNull(data.maturation_status);
  const role = useAuthStore((state) => state.user?.role);
  const isCoachViewer = role === UserRole.coach || role === UserRole.admin;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(data.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Si falla (permiso, browser viejo) silenciamos: no hay tracking en cliente.
    }
  }

  return (
    <article
      className={cn(
        "space-y-4 rounded-xl bg-white p-5 ring-1 ring-light-gray",
        className,
      )}
      data-testid="ai-generated-content"
    >
      <header className="flex flex-wrap items-center gap-2 text-xs text-mid-gray">
        <PHVBadge status={status} />
      </header>

      <div className="space-y-1">
        <p className="text-xs text-mid-gray" data-testid="ai-provenance">
          Generado por el asistente de IA del club ·{" "}
          <span aria-label="Fecha de generación">
            {formatDateTime(data.generated_at)}
          </span>
        </p>

        {isCoachViewer && (
          <details
            className="text-xs text-mid-gray"
            data-testid="ai-technical-details"
          >
            <summary className="inline-flex min-h-8 w-fit cursor-pointer select-none items-center rounded-md font-medium text-charcoal hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
              Detalles técnicos
            </summary>
            <dl className="mt-1.5 space-y-1 pl-3">
              <div className="flex flex-wrap gap-x-1">
                <dt className="font-medium text-charcoal">Modelo:</dt>
                <dd>
                  {data.provider}/{data.model}
                </dd>
              </div>
              <div className="flex flex-wrap gap-x-1">
                <dt className="font-medium text-charcoal">
                  Versión del prompt:
                </dt>
                <dd>{data.prompt_version ?? "No disponible"}</dd>
              </div>
              <div className="flex flex-wrap gap-x-1">
                <dt className="font-medium text-charcoal">
                  Referencia de traza:
                </dt>
                <dd>{data.trace_id ?? "No disponible"}</dd>
              </div>
            </dl>
          </details>
        )}
      </div>

      <div
        role="alert"
        className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900"
      >
        Generado por IA basándose en datos del atleta. Revisa con el
        entrenador antes de tomar decisiones.
      </div>

      <div className="text-sm leading-relaxed text-charcoal">
        <ReactMarkdown
          components={{
            p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
            strong: ({ children }) => (
              <strong className="font-semibold text-charcoal">{children}</strong>
            ),
            em: ({ children }) => <em className="italic">{children}</em>,
            ul: ({ children }) => (
              <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">
                {children}
              </ol>
            ),
            li: ({ children }) => <li>{children}</li>,
            h1: ({ children }) => (
              <h1 className="mb-2 text-base font-semibold">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="mb-2 text-base font-semibold">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="mb-2 text-sm font-semibold">{children}</h3>
            ),
            code: ({ children }) => (
              <code className="rounded bg-light-gray px-1 py-0.5 text-xs">
                {children}
              </code>
            ),
          }}
        >
          {data.text}
        </ReactMarkdown>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleCopy}
          className="min-h-12 rounded-lg border border-light-gray px-4 text-sm font-medium text-charcoal hover:bg-light-gray/40 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
    </article>
  );
}
