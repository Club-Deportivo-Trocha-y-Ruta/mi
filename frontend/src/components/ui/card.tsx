/**
 * Card — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * Aplica por defecto (alineado con `page/src/components/common/Card.astro`):
 *  - `rounded-card`
 *  - `bg-surface-raised` (flota sobre la página; en dark queda más clara
 *    que la superficie base — ver style.css)
 *  - `shadow-card` + `ring-1 ring-hairline`
 *
 * Sin hover-lift por defecto: en la app las cards no siempre son clicables
 * (a diferencia de page, donde `href` activa el lift). Si un consumidor
 * necesita ese efecto, lo añade vía `className`.
 *
 * Estos defaults reemplazan el `CARD_SHADOW` hardcoded que estaba duplicado
 * en ~8 archivos. Wave 1 entrega el primitivo; las migraciones de páginas a
 * <Card> se harán en waves posteriores.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-card bg-surface-raised text-charcoal shadow-card ring-1 ring-hairline",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("flex flex-col gap-1 px-5 py-4", className)} {...props} />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("text-base font-semibold text-charcoal", className)}
    {...props}
  />
));
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-mid-gray", className)}
    {...props}
  />
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("px-5 py-4", className)} {...props} />
));
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center px-5 py-4", className)}
    {...props}
  />
));
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter };
