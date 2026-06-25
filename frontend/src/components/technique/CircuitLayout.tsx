/**
 * CircuitLayout — muestra el diagrama ASCII de una gymkhana junto con su
 * leyenda compartida.
 *
 * Criterios de aceptación (T021):
 *  - layout_ascii se renderiza en <pre> monoespaciado, responsive
 *    (overflow-x: auto, white-space: pre) — nunca rompe el layout en móvil.
 *  - El bloque <pre> tiene role="img" y aria-label derivado de layout_alt
 *    (alternativa de texto WCAG 2.1 AA); adicionalmente un <span> visually-
 *    hidden repite layout_alt para lectores de pantalla que ignoran role="img"
 *    en elementos no-img nativos.
 *  - Si el ejercicio NO es gymkhana, o layout_ascii es null/vacío, el
 *    componente retorna null (nada que renderizar).
 *  - La leyenda se renderiza siempre que haya layout (FR-008).
 */

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
 * Renderiza el layout ASCII de la gymkhana junto con la leyenda compartida.
 * Retorna null si el ejercicio no es gymkhana o no tiene layout.
 */
export function CircuitLayout({ exercise }: CircuitLayoutProps) {
  const { is_gymkhana, layout_ascii, layout_alt } = exercise;

  if (!is_gymkhana || !layout_ascii?.trim()) {
    return null;
  }

  const altText = layout_alt?.trim() || "Diagrama del circuito de gymkhana";

  return (
    <section aria-label="Circuito y leyenda" className="space-y-0">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">
        Diagrama del circuito
      </h3>

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

      <CircuitLegend />
    </section>
  );
}

export default CircuitLayout;
