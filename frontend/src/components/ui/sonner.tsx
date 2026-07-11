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
          toast:
            "rounded-xl border border-[rgba(34,42,53,0.08)] bg-white text-charcoal shadow-card",
          title: "text-sm font-medium text-charcoal",
          description: "text-sm text-mid-gray",
          success: "!border-green-200",
          error: "!border-red-200",
          actionButton: "!bg-primary !text-white",
          cancelButton: "!bg-light-gray !text-charcoal",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
