/**
 * Skeleton — placeholder de carga accesible.
 *
 * Características:
 *   - **Silencioso para lectores de pantalla** (`aria-hidden="true"`). Cuando
 *     se renderizan N skeletons (ej. una grid de cards), anunciar "Cargando…"
 *     N veces es ruido. El consumidor debe envolver el bloque que carga con
 *     un único `<div role="status" aria-busy="true" aria-label="Cargando…">`
 *     a nivel de sección — un solo anuncio por estado de carga.
 *   - Respeta `prefers-reduced-motion` (sin animación si el usuario opta out).
 *   - Forma rectangular básica — el consumidor decide tamaño con `className`.
 *
 * Patrón shadcn estándar. Reemplaza los `animate-pulse bg-light-gray` sueltos
 * que están repetidos por el código.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

const Skeleton = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={cn(
        "animate-pulse rounded bg-light-gray motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
});
Skeleton.displayName = "Skeleton";

export { Skeleton };
