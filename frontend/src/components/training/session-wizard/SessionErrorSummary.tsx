import { AlertCircle } from "lucide-react";

export interface ErrorSummaryItem {
  /** Nombre del campo (para foco) y mensaje localizado. */
  field: string;
  message: string;
  /** id del input asociado para enfocar/revelar. */
  targetId: string;
}

interface SessionErrorSummaryProps {
  items: ErrorSummaryItem[];
}

/**
 * Resumen persistente y escaneable de lo que falta para guardar. Al pulsar un
 * ítem, enfoca/revela el campo correspondiente. Se muestra cuando el intento de
 * avanzar/guardar está bloqueado.
 */
export function SessionErrorSummary({ items }: SessionErrorSummaryProps) {
  if (items.length === 0) return null;

  function focusField(targetId: string) {
    const el = document.getElementById(targetId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      // El foco mejora accesibilidad; algunos contenedores no son focusables,
      // por eso el try/catch defensivo.
      try {
        (el as HTMLElement).focus({ preventScroll: true });
      } catch {
        /* noop */
      }
    }
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="rounded-lg border border-red-200 bg-red-50 px-4 py-3"
      data-testid="session-error-summary"
    >
      <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-red-800">
        <AlertCircle size={16} aria-hidden="true" />
        Revisa estos campos antes de continuar
      </div>
      <ul className="space-y-1 text-sm text-red-700">
        {items.map((it) => (
          <li key={it.field}>
            <button
              type="button"
              onClick={() => focusField(it.targetId)}
              className="text-left underline decoration-red-300 underline-offset-2 hover:decoration-red-600"
            >
              {it.message}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
