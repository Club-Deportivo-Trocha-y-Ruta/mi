/**
 * Input — primitivo shadcn/ui adaptado a los tokens de Trocha y Ruta.
 *
 * h-12 (48px) por defecto — cumple el mínimo de touch target del proyecto.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          "flex h-12 w-full min-w-0 rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 py-2 text-sm text-charcoal shadow-ring transition-colors",
          "placeholder:text-mid-gray",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "aria-invalid:border-red-500 aria-invalid:ring-2 aria-invalid:ring-red-500/30",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
