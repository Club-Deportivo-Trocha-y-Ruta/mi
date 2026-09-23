/**
 * Button — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * Tamaños:
 *   - default → h-11 (≥44px touch target)
 *   - sm      → h-9   (uso interno en toolbars muy compactas)
 *   - lg      → h-12  (CTA principales)
 *   - icon    → 44×44 (botones cuadrados con icono)
 *
 * Variantes:
 *   - default     → marca primaria (turquesa). El teal vivo (`--color-primary`)
 *     solo da ~2.4:1 de contraste contra blanco, por eso el texto va en
 *     `text-surface-dark` (grafito, no blanco) — mismo criterio que
 *     `page/src/components/common/Button.astro`.
 *   - destructive → rojo (Tailwind red-600, fijo en ambos temas — no es un
 *     token remapeable, por eso `text-white` sí es seguro aquí)
 *   - outline     → contorno + texto en `primary-deep` (accesible sobre
 *     fondos claros), como el outline de page
 *   - secondary   → gris claro
 *   - ghost       → sin fondo
 *   - link        → texto teal subrayado en hover
 *
 * Foco visible con `outline` (no `ring`), como page: el offset dibuja el
 * anillo fuera del botón, así funciona incluso en la variante `default`
 * (bg-primary) sin perder visibilidad contra el fondo primary.
 *
 * Botón "físico" (shadow-pressable + micro-viaje al presionar, ver
 * page/src/components/common/Button.astro) solo en la variante `default`:
 * es la CTA principal, no tiene sentido en variantes secundarias/ghost/link.
 */
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// Transición + micro-viaje del botón "físico": solo transitiona
// `transform`, nunca `box-shadow` (barato de animar). `motion-reduce:*`
// anula el desplazamiento sin desactivar el botón.
const pressable = [
  "shadow-pressable [--btn-shadow-color:var(--color-primary-dark)]",
  "transition-transform duration-[var(--duration-micro)] ease-spring",
  "hover:-translate-y-px active:translate-y-1 active:shadow-none",
  "motion-reduce:transition-none motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
].join(" ");

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control",
    "text-sm font-semibold transition-colors",
    "focus-visible:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "disabled:pointer-events-none disabled:opacity-50",
  ].join(" "),
  {
    variants: {
      variant: {
        default: cn(
          "bg-primary text-surface-dark hover:bg-primary-deep hover:text-on-deep",
          pressable,
        ),
        destructive: "bg-red-600 text-white hover:bg-red-700",
        outline:
          "border-2 border-primary-deep bg-transparent text-primary-deep hover:bg-primary-deep hover:text-on-deep",
        secondary: "bg-light-gray text-charcoal hover:bg-surface-muted",
        ghost: "bg-transparent text-charcoal hover:bg-light-gray",
        link: "bg-transparent text-link-blue underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-11 px-4 py-2",
        sm: "h-9 px-3 text-sm",
        lg: "min-h-12 px-6 text-base",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
