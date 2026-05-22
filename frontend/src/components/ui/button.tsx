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
 *   - default     → marca primaria (turquesa)
 *   - destructive → rojo
 *   - outline     → contorno + hover gris claro
 *   - secondary   → gris claro
 *   - ghost       → sin fondo
 *   - link        → texto azul subrayado en hover
 *
 * Focus visible centralizado con el outline del sistema (var(--color-primary)).
 */
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg",
    "text-sm font-medium transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2",
    "disabled:pointer-events-none disabled:opacity-50",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-primary text-white hover:bg-primary-dark",
        destructive: "bg-red-600 text-white hover:bg-red-700",
        outline:
          "border border-[rgba(34,42,53,0.12)] bg-white text-charcoal hover:bg-light-gray",
        secondary: "bg-light-gray text-charcoal hover:bg-[#e8e8e8]",
        ghost: "bg-transparent text-charcoal hover:bg-light-gray",
        link: "bg-transparent text-link-blue underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-11 px-4 py-2",
        sm: "h-9 rounded-md px-3 text-sm",
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
