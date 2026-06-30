/**
 * CircuitLayout — muestra el diagrama de circuito de una gymkhana junto con
 * su leyenda compartida.
 *
 * Criterios de aceptación (T018 / T021):
 *  - Cuando layout_json está presente (feature 019), delega al componente
 *    <CircuitDiagram> (inline SVG, responsive, a11y WCAG 2.1 AA).
 *  - Cuando layout_json es null pero layout_ascii no está vacío, mantiene
 *    el legacy <pre> monoespaciado con role="img" y aria-label (fallback ASCII).
 *  - Si el ejercicio NO es gymkhana, o no hay ningún layout disponible,
 *    el componente retorna null (nada que renderizar).
 *  - La leyenda ASCII solo se renderiza en el camino de fallback; CircuitDiagram
 *    expone su propia leyenda de elementos vectoriales.
 */

import { CircuitDiagram } from "@/components/technique/CircuitDiagram";
import type { ExerciseDetail } from "@/types/technique.types";

interface CircuitLayoutProps {
  exercise: ExerciseDetail;
}

/** Texto visually hidden — accesible para lectores de pantalla, invisible visualmente. */
function VisuallyHidden({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="absolute -m-px h-px w-px overflow-hidden whitespace-nowrap border-0 p-0"
      style={{ clip: "rect(0 0 0 0)", clipPath: "inset(50%)" }}
    >
      {children}
    </span>
  );
}

/** Leyenda compartida de símbolos del circuito. Seeded content in español. */
function CircuitLegend() {
  const symbols = [
    { symbol: "S", description: "Inicio / Salida" },
    { symbol: "F", description: "Llegada / Fin" },
    { symbol: "→", description: "Dirección de recorrido" },
    { symbol: "[ ]", description: "Estación / obstáculo" },
    { symbol: "( )", description: "Zona de maniobra" },
    { symbol: "---", description: "Trayecto libre" },
    { symbol: "===", description: "Trayecto técnico (precisión)" },
  ];

  return (
    <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Leyenda del circuito
      </p>
      <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
        {symbols.map(({ symbol, description }) => (
          <li key={symbol} className="flex items-baseline gap-2 text-xs text-slate-600">
            <code className="shrink-0 rounded bg-white px-1.5 py-0.5 font-mono text-xs font-medium text-slate-800 ring-1 ring-slate-200">
              {symbol}
            </code>
            <span>{description}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Renderiza el diagrama de la gymkhana junto con la leyenda compartida.
 *
 * Regla de selección de renderer (FR-010):
 *   1. layout_json presente → <CircuitDiagram> (inline SVG, feature 019).
 *   2. layout_json null + layout_ascii no vacío → legacy <pre> + CircuitLegend.
 *   3. Sin ningún layout (o no es gymkhana) → null.
 */
export function CircuitLayout({ exercise }: CircuitLayoutProps) {
  const { is_gymkhana, layout_json, layout_ascii, layout_alt } = exercise;

  // Guard: solo gymkhana con al menos un layout disponible
  const hasSvgLayout = Boolean(layout_json);
  const hasAsciiLayout = Boolean(layout_ascii?.trim());

  if (!is_gymkhana || (!hasSvgLayout && !hasAsciiLayout)) {
    return null;
  }

  const altText = layout_alt?.trim() || "Diagrama del circuito de gymkhana";

  return (
    <section aria-label="Circuito y leyenda" className="space-y-0">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">
        Diagrama del circuito
      </h3>

      {/* ── Camino principal: SVG estructurado (feature 019) ────────────── */}
      {hasSvgLayout && layout_json ? (
        <CircuitDiagram layout={layout_json} altText={altText} />
      ) : (
        /* ── Fallback: ASCII monoespaciado (feature 018) ───────────────── */
        <>
          {/* Contenedor con scroll horizontal — evita overflow en pantallas estrechas */}
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-950">
            {/*
              role="img" convierte el <pre> en una imagen accesible.
              aria-label provee la descripción textual requerida por WCAG 1.1.1.
              El <VisuallyHidden> es un fallback para SRs que no honran role="img"
              en elementos no-img nativos (ej. NVDA + Firefox).
            */}
            <pre
              role="img"
              aria-label={altText}
              className="whitespace-pre p-4 font-mono text-xs leading-snug text-slate-100 sm:text-sm"
            >
              <VisuallyHidden>{altText}</VisuallyHidden>
              {layout_ascii}
            </pre>
          </div>

          {/* La leyenda ASCII solo se muestra en el camino de fallback.
              CircuitDiagram tiene su propia leyenda vectorial integrada. */}
          <CircuitLegend />
        </>
      )}
    </section>
  );
}

export default CircuitLayout;
