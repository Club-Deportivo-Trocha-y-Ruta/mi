/**
 * Helpers puros extraídos del wizard de importación (B5).
 *
 * - `isRevisionDryRun`        — type-guard del dry-run union.
 * - `shouldWarnUnusualDiff`   — banner naranja si el diff supera umbrales.
 * - `formatCommittedAt`       — fecha local "es-CO" desde ISO.
 * - `getErrMsg`               — mensaje legible para errores del wizard.
 *
 * Vivos en archivo separado para mantener `ImportWizard.tsx` enfocado en
 * orquestación visual + state.
 */
import { getImportErrorMessage } from "@/lib/api/errorMessages";
import type {
  ImportDryRunResponse,
  ImportDryRunRevisionResponse,
} from "@/types/raceImports.types";

/**
 * Type guard — discrimina la union de dry-run response (matches vs revision).
 *
 * Backend marca `is_revision: true` solo en el branch revisión; en F-UP normal
 * el campo es `false` o ausente.
 */
export function isRevisionDryRun(
  data: ImportDryRunResponse | undefined,
): data is ImportDryRunRevisionResponse {
  return !!data && (data as ImportDryRunRevisionResponse).is_revision === true;
}

export const REVISION_REASON_MAX = 300;

/** Banner naranja si el diff es inusualmente grande (R1 mitigación). */
export function shouldWarnUnusualDiff(summary: {
  n_total: number;
  n_delete: number;
  n_unchanged: number;
}): boolean {
  if (summary.n_total > 500) return true;
  // Si hay deletes y exceden 20% del unchanged.
  if (summary.n_delete > 0 && summary.n_delete > summary.n_unchanged * 0.2) {
    return true;
  }
  return false;
}

export function formatCommittedAt(iso: string | undefined | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-CO", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

/**
 * Prioriza el `detail` del payload (string o array Pydantic) — vía
 * `getImportErrorMessage` — para preservar mensajes server-side específicos.
 * Si no hay detail explicativo, mapea status codes del wizard de ingesta
 * a copy en español; en último recurso, devuelve el fallback genérico.
 */
export function getErrMsg(err: unknown, fallback: string): string {
  // Status-specific fallback que usaremos si no hay detail informativo.
  let statusFallback = fallback;
  if (typeof err === "object" && err !== null) {
    const e = err as { response?: { status?: number } };
    if (e.response?.status === 409) {
      statusFallback = "Este PDF ya fue ingestado previamente.";
    } else if (e.response?.status === 500) {
      statusFallback =
        "Error interno al procesar la ingesta. Revisa el archivo o contacta soporte.";
    } else if (e.response?.status === 422) {
      statusFallback = "Datos inválidos. Revisa el formulario y vuelve a intentar.";
    }
  }
  // getImportErrorMessage extrae detail (string / Pydantic array) si existe;
  // si no, mapea 413 y como último recurso devuelve statusFallback.
  return getImportErrorMessage(err, statusFallback);
}
