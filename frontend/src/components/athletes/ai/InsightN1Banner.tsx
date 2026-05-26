/**
 * Banner informativo N=1 — se muestra arriba del summary en el detalle
 * del insight cuando el set lanzado tenía 1 sola válida.
 *
 * Razón: con n=1 no hay tendencia posible, por eso el análisis es
 * estrictamente descriptivo y no debe leerse como proyección.
 */
import { Info } from "lucide-react";

interface InsightN1BannerProps {
  mode: "coach" | "parent";
}

const COPY: Record<InsightN1BannerProps["mode"], string> = {
  coach:
    "Análisis basado en la primera válida de la temporada. Lectura descriptiva del desempeño puntual, no constituye proyección de tendencia.",
  parent:
    "Tu hijo/a ha corrido su primera válida de la temporada. Lo que ves aquí describe ese día; aún es pronto para hablar de evolución.",
};

export function InsightN1Banner({ mode }: InsightN1BannerProps) {
  return (
    <div
      role="note"
      data-testid="insight-n1-banner"
      className="flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900"
    >
      <Info size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
      <p className="leading-relaxed">{COPY[mode]}</p>
    </div>
  );
}
