/**
 * Badge — primitivo shadcn/ui con variantes alineadas al design system de
 * Trocha y Ruta.
 *
 * Variantes:
 *   - default      → marca primaria (turquesa)
 *   - secondary    → gris suave
 *   - destructive  → rojo (errores / acciones críticas)
 *   - outline      → contorno + texto charcoal
 *   - success      → verde (atleta presente, métrica positiva)
 *   - warning      → ámbar (atención, valor intermedio)
 *   - info         → azul (información, valor neutro)
 *
 * Las paletas success/warning/info usan tonos -100/-800/-900 que pasan WCAG AA
 * para tamaño de texto de 12px (el caso típico del badge).
 */
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary text-white",
        secondary: "bg-light-gray text-charcoal",
        destructive: "bg-red-100 text-red-800",
        outline:
          "border border-[rgba(34,42,53,0.12)] bg-transparent text-charcoal",
        success: "bg-green-100 text-green-800",
        warning: "bg-amber-100 text-amber-900",
        info: "bg-blue-100 text-blue-900",
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
