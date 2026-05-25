/**
 * Textarea — primitivo shadcn/ui adaptado a tokens Trocha y Ruta.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal",
          "placeholder:text-mid-gray outline-none transition-shadow",
          "focus:ring-2 focus:ring-link-blue/50",
          "disabled:bg-light-gray disabled:text-mid-gray disabled:cursor-not-allowed",
          "shadow-ring resize-y min-h-[80px]",
          "aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-red-500/40",
          className,
        )}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };
