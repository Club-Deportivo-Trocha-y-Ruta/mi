/**
 * Badge — primitivo shadcn/ui con variantes alineadas al design system de
 * Trocha y Ruta (patrón "tinte suave" de `page/src/components/common/Badge.astro`:
 * fondo al 10% de opacidad del token + texto legible).
 *
 * Variantes:
 *   - default      → marca primaria (turquesa), texto `primary-deep` (el
 *     teal vivo no cumple 4.5:1 como texto — mismo criterio que page)
 *   - secondary    → tinte neutro (`surface-tint` + `text-secondary`, patrón
 *     "neutral" de page)
 *   - destructive  → tinte rojo, texto `danger` (¬4.8:1 sobre el tinte, pasa AA)
 *   - outline      → contorno + texto charcoal (sin tinte: es la variante
 *     "borde solamente", page no tiene equivalente)
 *   - success      → tinte verde. `--color-success` (~3.4:1) no alcanza AA
 *     como texto a 12px — mismo hallazgo documentado en
 *     `components/shared/StatusBadge.tsx` — por eso el texto va en charcoal
 *     y el color solo vive en el tinte de fondo
 *   - warning      → tinte ámbar, mismo motivo que success (`--color-warning`
 *     ronda 1.8:1, ilegible como texto)
 *   - info         → tinte azul, texto `info` (cumple AA con margen amplio)
 */
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary/10 text-primary-deep",
        secondary: "bg-surface-tint text-text-secondary",
        destructive: "bg-danger/10 text-danger",
        outline: "border border-hairline bg-transparent text-charcoal",
        success: "bg-success/10 text-charcoal",
        warning: "bg-warning/10 text-charcoal",
        info: "bg-info/10 text-info",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
