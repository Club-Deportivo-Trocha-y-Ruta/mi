/**
 * Avisos del wizard cuando llega con `?import=<id>` (feature 045, US3):
 *  - `ResumeLoadingNotice`: retomando (cold start: nunca un spinner pelado).
 *  - `ResumeStatusNotice`: la carga no se puede retomar (ya confirmada,
 *    descartada, fallida) o no existe / es de otro club. Con `legacy`
 *    (amendment 2026-09-26, `restage_required`), muestra el aviso de
 *    carga preparada con el método anterior — solo se ofrece *Descartar*,
 *    nunca «Empezar una carga nueva» (no hay dónde empezar de nuevo: la
 *    carga se prepara fuera de la app).
 */
import { Link } from "react-router-dom";
import { AlertCircle, Info, Trash2 } from "lucide-react";

import type { ImportDetail } from "@/types/raceImports.types";

/** Amendment 2026-09-26 — carga preparada con el método anterior. */
export const LEGACY_NOTICE_MESSAGE =
  "Esta carga se preparó con el método anterior y ya no se puede revisar. Descártala y pide que se prepare de nuevo.";

export function ResumeLoadingNotice() {
  return (
    <div
      className="space-y-3"
      role="status"
      aria-live="polite"
      data-testid="resume-loading"
    >
      <p className="text-sm text-mid-gray">
        Retomando tu carga… Si el servidor estaba inactivo, esto puede tardar
        unos segundos.
      </p>
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="h-12 animate-pulse rounded-lg bg-light-gray"
          aria-hidden="true"
        />
      ))}
    </div>
  );
}

export interface ResumeStatusNoticeProps {
  /** Detalle de la carga, si el servidor respondió. `undefined` con `isError` = no existe. */
  detail?: ImportDetail;
  isError: boolean;
  /** Descarta el parámetro `import` y navega al tablero (`?seccion=cargas`). */
  onStartNew: () => void;
  /**
   * Amendment 2026-09-26 — carga legacy (`restage_required`): muestra el
   * aviso de método anterior y solo ofrece *Descartar* (vía `onDiscard`),
   * nunca «Empezar una carga nueva».
   */
  legacy?: boolean;
  /** Requerido cuando `legacy` — abre el diálogo de descarte. */
  onDiscard?: () => void;
}

const STATUS_COPY: Partial<Record<ImportDetail["status"], string>> = {
  committed: "Esta carga ya se confirmó.",
  discarded: "Esta carga se descartó.",
  failed: "Esta carga no se pudo leer. Sube el archivo de nuevo.",
};

export function ResumeStatusNotice({
  detail,
  isError,
  onStartNew,
  legacy = false,
  onDiscard,
}: ResumeStatusNoticeProps) {
  const message = legacy
    ? LEGACY_NOTICE_MESSAGE
    : isError
      ? "No encontramos esa carga. Puede que ya no exista o que sea de otro club."
      : (detail && STATUS_COPY[detail.status]) ||
        "Esta carga no se puede retomar.";
  const Icon = isError ? AlertCircle : Info;

  return (
    <div
      role={isError ? "alert" : "status"}
      className={
        isError
          ? "space-y-3 rounded-lg border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-800"
          : "space-y-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900"
      }
      data-testid="resume-status-notice"
    >
      <div className="flex items-start gap-2">
        <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
        <p>{message}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {legacy ? (
          <button
            type="button"
            onClick={onDiscard}
            className="inline-flex min-h-12 items-center gap-1.5 rounded-lg bg-surface-raised px-3 py-2 text-xs font-medium text-red-700 ring-1 ring-light-gray hover:bg-red-50"
            data-testid="resume-legacy-discard"
          >
            <Trash2 size={14} aria-hidden="true" />
            Descartar esta carga
          </button>
        ) : (
          <>
            {detail?.status === "committed" && detail.event_id != null && (
              <Link
                to={`/competitions/${detail.event_id}?tab=results`}
                className="inline-flex min-h-12 items-center rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-surface hover:opacity-90"
                data-testid="resume-view-results"
              >
                Ver resultados de la competencia
              </Link>
            )}
            <button
              type="button"
              onClick={onStartNew}
              className="inline-flex min-h-12 items-center rounded-lg bg-surface-raised px-3 py-2 text-xs font-medium text-charcoal ring-1 ring-light-gray hover:bg-light-gray"
              data-testid="resume-start-new"
            >
              Empezar una carga nueva
            </button>
          </>
        )}
      </div>
    </div>
  );
}
