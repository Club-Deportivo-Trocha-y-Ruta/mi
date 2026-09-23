/**
 * Toaster — wrapper de `sonner` con tokens de Trocha y Ruta. Reemplaza los
 * toasts locales hand-rolled repartidos por la app (ver research.md R2).
 * Uso: `toast.success(msg)` / `toast.error(msg)` desde cualquier componente.
 */
import { Toaster as Sonner, type ToasterProps } from "sonner";

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "rounded-card border border-hairline bg-surface-raised text-charcoal shadow-card",
          title: "text-sm font-medium text-charcoal",
          description: "text-sm text-mid-gray",
          success: "!border-success/30",
          error: "!border-danger/30",
          // Texto oscuro sobre bg-primary (no blanco): mismo criterio que
          // Button/Checkbox — el teal vivo no cumple contraste con blanco.
          actionButton: "!bg-primary !text-surface-dark",
          cancelButton: "!bg-light-gray !text-charcoal",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
