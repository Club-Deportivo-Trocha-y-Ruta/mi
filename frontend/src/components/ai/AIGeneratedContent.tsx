import { useState } from "react";

import { PHVBadge } from "@/components/shared/PHVBadge";
import { cn } from "@/lib/utils";
import type { PHVExplanationResponse } from "@/types/ai.types";
import { MaturationStatus } from "@/types/enums";

interface AIGeneratedContentProps {
  data: PHVExplanationResponse;
  className?: string;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-CO", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
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
 * Renderiza: badge PHV, modelo, fecha relativa, disclaimer obligatorio,
 * texto y botón "Copiar". El disclaimer NO es ocultable (responsabilidad
 * del componente, no del consumidor).
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
        <span
          className="rounded-full bg-purple-100 px-2.5 py-1 font-medium text-purple-700"
          aria-label="Generado por IA"
        >
          IA · {data.provider}/{data.model}
        </span>
        <span className="ml-auto" aria-label="Fecha de generación">
          {formatDate(data.generated_at)}
        </span>
      </header>

      <div
        role="alert"
        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      >
        Generado por IA basándose en datos del atleta. Revisa con el
        entrenador antes de tomar decisiones.
      </div>

      <div className="whitespace-pre-wrap text-sm leading-relaxed text-charcoal">
        {data.text}
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-lg border border-light-gray px-3 py-1.5 text-xs font-medium text-charcoal hover:bg-light-gray/40 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
    </article>
  );
}
