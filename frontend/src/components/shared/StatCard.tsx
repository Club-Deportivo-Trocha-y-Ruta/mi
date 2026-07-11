import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

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
}

export function StatCard({ label, value, hint, isLoading = false, href }: StatCardProps) {
  const body = (
    <CardContent className="flex flex-col gap-1">
      <p className="text-sm text-mid-gray">{label}</p>
      {isLoading ? (
        <Skeleton className="h-8 w-20" />
      ) : (
        <p className="font-display text-2xl font-semibold text-charcoal">{value}</p>
      )}
      {hint && <p className="text-xs text-mid-gray">{hint}</p>}
    </CardContent>
  );

  return (
    <Card className={cn("shadow-card", href && "transition-shadow hover:shadow-ring")}>
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
