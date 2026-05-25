/**
 * ToastBanner — banner aria-live="polite" sin librería externa.
 *
 * Variantes: success | error | info. Cierra al hacer click en X.
 * Extraído de UnlinkedCompetitorsTab en B5.
 */
import { AlertTriangle, CheckCircle2, Link2, X } from "lucide-react";

import { cn } from "@/lib/utils";

export type ToastVariant = "success" | "error" | "info";

export interface ToastState {
  variant: ToastVariant;
  message: string;
}

export interface ToastBannerProps {
  toast: ToastState | null;
  onDismiss: () => void;
}

export function ToastBanner({ toast, onDismiss }: ToastBannerProps) {
  if (!toast) return null;
  const palette =
    toast.variant === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : toast.variant === "error"
        ? "border-red-200 bg-red-50 text-red-800"
        : "border-blue-200 bg-blue-50 text-blue-800";
  const Icon =
    toast.variant === "success"
      ? CheckCircle2
      : toast.variant === "error"
        ? AlertTriangle
        : Link2;
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid={`toast-${toast.variant}`}
      className={cn(
        "flex items-start gap-2 rounded-xl border px-4 py-3 text-sm",
        palette,
      )}
    >
      <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span className="flex-1">{toast.message}</span>
      <button
        type="button"
        aria-label="Cerrar notificación"
        onClick={onDismiss}
        className="shrink-0 rounded p-0.5 transition-colors hover:bg-black/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
