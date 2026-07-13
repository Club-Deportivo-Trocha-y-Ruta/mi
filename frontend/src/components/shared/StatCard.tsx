import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Status } from "@/components/shared/StatusBadge";

/**
 * StatCard — tile de métrica reutilizable (label + valor + hint opcional).
 * Si se pasa `href`, la tarjeta completa se envuelve en un solo Link
 * (≥48px de alto) en vez de exponer un CTA interno pequeño; sin `href`
 * queda como un div no interactivo. API congelada — una feature futura
 * suma slots opcionales de delta/urgencia, así que no se sella contra
 * props adicionales.
 */
interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  /** Estado de carga: reemplaza el valor por un Skeleton. */
  isLoading?: boolean;
  /** Si se pasa, toda la tarjeta se envuelve en un Link a esta ruta. */
  href?: string;
  /**
   * Slot aditivo de urgencia (feature 031, `contracts/home-tiles.md` Tile 2
   * "Próxima carrera"). Agrega un acento de color en el borde izquierdo de
   * la tarjeta. `undefined`/`"neutral"`/`"success"` no cambian el estilo por
   * defecto — retrocompatible con todos los consumidores existentes.
   */
  tone?: Status;
  /**
   * Slot aditivo (feature 031): contenido extra (p. ej. un `StatusBadge`)
   * renderizado debajo del hint. El color nunca es el único canal — este
   * slot existe precisamente para acompañar `tone` con ícono + texto
   * (Constitution III).
   */
  badge?: ReactNode;
}

const TONE_ACCENT_CLASSES: Partial<Record<Status, string>> = {
  warning: "border-l-4 border-l-warning",
  danger: "border-l-4 border-l-danger",
};

export function StatCard({
  label,
  value,
  hint,
  isLoading = false,
  href,
  tone,
  badge,
}: StatCardProps) {
  const body = (
    <CardContent className="flex flex-col gap-1">
      <p className="text-sm text-mid-gray">{label}</p>
      {isLoading ? (
        <Skeleton className="h-8 w-20" />
      ) : (
        <p className="font-display text-2xl font-semibold text-charcoal">{value}</p>
      )}
      {hint && <p className="text-xs text-mid-gray">{hint}</p>}
      {badge && <div className="mt-1">{badge}</div>}
    </CardContent>
  );

  return (
    <Card
      className={cn(
        "shadow-card",
        href && "transition-shadow hover:shadow-ring",
        tone && TONE_ACCENT_CLASSES[tone],
      )}
    >
      {href ? (
        <Link
          to={href}
          className="block min-h-12 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2"
        >
          {body}
        </Link>
      ) : (
        body
      )}
    </Card>
  );
}
