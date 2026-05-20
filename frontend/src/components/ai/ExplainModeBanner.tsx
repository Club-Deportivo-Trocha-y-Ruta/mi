/**
 * Banner sticky con toggle "Modo aprendizaje" (race-analysis §10.2 #ExplainModeBanner).
 *
 * Persiste en localStorage vía `useExplainModeStore`. Cuando está
 * activo, el componente cambia color e incluye copy explicando el
 * comportamiento esperado (narración + HITL siempre activo).
 */
import { GraduationCap, Info } from "lucide-react";

import { useExplainModeStore } from "@/store/explainMode.store";
import { cn } from "@/lib/utils";

interface ExplainModeBannerProps {
  className?: string;
}

export function ExplainModeBanner({ className }: ExplainModeBannerProps) {
  const enabled = useExplainModeStore((s) => s.enabled);
  const toggle = useExplainModeStore((s) => s.toggle);

  return (
    <div
      role="region"
      aria-label="Modo aprendizaje"
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 text-sm transition-colors",
        enabled
          ? "bg-amber-50 text-amber-900 ring-1 ring-amber-200"
          : "bg-light-gray/40 text-charcoal ring-1 ring-light-gray",
        className,
      )}
      data-testid="explain-mode-banner"
    >
      <GraduationCap
        size={18}
        aria-hidden="true"
        className={enabled ? "text-amber-700" : "text-mid-gray"}
      />
      <div className="flex-1 min-w-[200px]">
        <p className="font-semibold">
          Modo aprendizaje {enabled ? "activo" : "desactivado"}
        </p>
        {enabled ? (
          <p className="mt-0.5 text-xs leading-relaxed text-amber-900">
            El agente narra qué hace en cada nodo del grafo y pausa para tu
            aprobación en cada paso clave.
          </p>
        ) : (
          <p className="mt-0.5 text-xs leading-relaxed text-mid-gray">
            Actívalo para ver explicaciones pedagógicas paso a paso.
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={toggle}
        aria-pressed={enabled}
        aria-label={
          enabled
            ? "Desactivar modo aprendizaje"
            : "Activar modo aprendizaje"
        }
        data-testid="explain-mode-toggle"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500",
          enabled
            ? "bg-amber-700 text-white hover:bg-amber-800"
            : "bg-charcoal text-white hover:opacity-90",
        )}
      >
        <Info size={14} aria-hidden="true" />
        {enabled ? "Desactivar" : "Activar"}
      </button>
    </div>
  );
}
