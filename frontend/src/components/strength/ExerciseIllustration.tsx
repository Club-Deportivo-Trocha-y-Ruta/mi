/**
 * ExerciseIllustration — muestra la figura ASCII original de un ejercicio de
 * fuerza (feature 021 / T016, FR-006).
 *
 * Mirror del fallback ASCII de `components/technique/CircuitLayout.tsx`
 * (feature 018): `<pre>` monoespaciado envuelto en `role="img"` +
 * `aria-label` tomado de `illustration_alt` (Constitution III — alt text
 * obligatorio). No hay camino SVG estructurado en 021 (`illustration_ascii`
 * es el único formato, ver data-model.md) — a diferencia de CircuitLayout no
 * existe rama `layout_json`.
 */

interface ExerciseIllustrationProps {
  illustration_ascii: string;
  illustration_alt: string;
}

/** Texto visualmente oculto — accesible para lectores de pantalla, invisible visualmente. */
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

/**
 * Renderiza la figura ASCII del ejercicio. Si no hay figura disponible,
 * retorna null (nada que renderizar).
 */
export function ExerciseIllustration({
  illustration_ascii,
  illustration_alt,
}: ExerciseIllustrationProps) {
  const hasIllustration = Boolean(illustration_ascii?.trim());

  if (!hasIllustration) {
    return null;
  }

  const altText = illustration_alt?.trim() || "Figura del ejercicio de fuerza";

  return (
    <section aria-label="Figura del ejercicio" className="space-y-0">
      <h3 className="mb-2 text-sm font-semibold text-charcoal">Figura</h3>

      {/*
        role="img" convierte el <pre> en una imagen accesible.
        aria-label provee la descripción textual requerida por WCAG 1.1.1.
        El <VisuallyHidden> es un fallback para SRs que no honran role="img"
        en elementos no-img nativos (ej. NVDA + Firefox).
      */}
      <div className="overflow-x-auto rounded-lg border border-border-gray bg-charcoal">
        <pre
          role="img"
          aria-label={altText}
          className="whitespace-pre p-4 font-mono text-xs leading-snug text-white sm:text-sm"
        >
          <VisuallyHidden>{altText}</VisuallyHidden>
          {illustration_ascii}
        </pre>
      </div>
    </section>
  );
}

export default ExerciseIllustration;
