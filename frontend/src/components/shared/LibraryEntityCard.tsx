/**
 * LibraryEntityCard — tarjeta compacta genérica para catálogos tipo
 * biblioteca (feature 033 / T040).
 *
 * Extraído de `components/technique/ExerciseCard.tsx` y
 * `components/strength/ExerciseCard.tsx` (mismo shell: enlace explícito
 * sobre el nombre + fila de badges superior + resumen + grupos de chips +
 * fila inferior, "mirror" documentado entre ambos). El dominio (dificultad
 * vs. equipo, habilidades vs. categoría de movimiento, gymkhana/juego vs.
 * duración/repeticiones) se pasa por props — este componente no conoce
 * técnica ni fuerza.
 *
 * WCAG: área de clic mínima 48×48 px (`min-h-12` + `flex items-center` en el
 * enlace del título). La tarjeta entera NO es clickable como un solo
 * elemento; el enlace es explícito sobre el nombre, manteniendo la
 * semántica correcta para lectores de pantalla (uso de `Link` de
 * react-router, no `<a href>`).
 */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface LibraryEntityCardChip {
  key: string;
  label: string;
}

export interface LibraryEntityCardChipGroup {
  /** aria-label for the chip row, e.g. "Franjas de edad" / "Habilidades". */
  ariaLabel: string;
  chips: LibraryEntityCardChip[];
  /** Rendered per chip; defaults to the badge look each domain already used. */
  renderChip?: (chip: LibraryEntityCardChip) => ReactNode;
}

interface LibraryEntityCardProps {
  href: string;
  title: string;
  /**
   * Rendered top-right, beside the title — the difficulty/equipment badge
   * plus any edit/attach icon-buttons (domain-specific, composed by the
   * caller with `Badge`/`Button`).
   */
  cornerContent?: ReactNode;
  summary?: string;
  chipGroups?: LibraryEntityCardChipGroup[];
  /**
   * Content beneath the summary/chips, pinned to the bottom of the card —
   * técnica's Gymkhana/Juego/Sin material indicator pills, or fuerza's
   * duration/reps line.
   */
  footer?: ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function defaultRenderChip(chip: LibraryEntityCardChip) {
  return (
    <span
      key={chip.key}
      className="inline-flex items-center rounded-full border border-border-gray bg-light-gray px-2 py-0.5 text-[11px] font-medium text-mid-gray"
    >
      {chip.label}
    </span>
  );
}

export function LibraryEntityCard({ href, title, cornerContent, summary, chipGroups, footer }: LibraryEntityCardProps) {
  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-2 py-4">
        {/* Name + corner content row */}
        <div className="flex items-start justify-between gap-2">
          <Link
            to={href}
            className="min-h-12 flex items-center text-sm font-semibold text-charcoal leading-snug hover:text-primary focus-visible:outline-none focus-visible:underline"
          >
            {title}
          </Link>
          {cornerContent && <div className="flex shrink-0 items-center gap-1">{cornerContent}</div>}
        </div>

        {/* Summary */}
        {summary && <p className="line-clamp-2 text-xs text-mid-gray">{summary}</p>}

        {/* Chip groups */}
        {chipGroups?.map((group, i) =>
          group.chips.length > 0 ? (
            <div key={i} className="flex flex-wrap gap-1" aria-label={group.ariaLabel}>
              {group.chips.map((chip) => (group.renderChip ?? defaultRenderChip)(chip))}
            </div>
          ) : null,
        )}

        {/* Footer — indicator pills / duration-reps line, always pinned to bottom */}
        {footer && <div className={cn("mt-auto pt-1")}>{footer}</div>}
      </CardContent>
    </Card>
  );
}

export default LibraryEntityCard;
