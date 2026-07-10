/**
 * InstructivoDownloadButton — descarga del instructivo PDF por marca (US3).
 *
 * Combina un selector de marca de ciclocomputador (Garmin / Magene / iGPSport)
 * con un botón de descarga. Al descargar:
 *   1. Pide el `Blob` al backend vía `useDownloadInstructivo` (API `downloadInstructivo`).
 *   2. Lo entrega al navegador con `triggerBlobDownload` (`lib/download.ts`).
 *
 * Estados:
 *   - Deshabilitado cuando la sesión no tiene estructura (`hasStructure=false`),
 *     espejando el guard del servidor (404 sin estructura). Copy explicativo.
 *   - `loading` mientras la mutación está en vuelo (botón + selector inertes).
 *   - `error` con copy en español neutro mapeado desde el error de Axios.
 *
 * RBAC: todo `/api/intervals` es coach/admin; el backend responde 403 a
 * padres/atletas. Este control se renderiza solo dentro de vistas de coach.
 */
import * as React from "react";
import { AlertCircle, Download, Loader2 } from "lucide-react";

import { mapIntervalError } from "@/api/intervals";
import { Button } from "@/components/ui/button";
import { triggerBlobDownload } from "@/lib/download";
import { useDownloadInstructivo } from "@/hooks/intervals/useIntervals";
import { cn } from "@/lib/utils";
import type { InstructivoBrand } from "@/types/intervals.types";

/** Marcas soportadas + etiqueta visible (español neutro). */
const BRAND_OPTIONS: ReadonlyArray<{ value: InstructivoBrand; label: string }> = [
  { value: "garmin", label: "Garmin" },
  { value: "magene", label: "Magene" },
  { value: "igpsport", label: "iGPSport" },
];

export interface InstructivoDownloadButtonProps {
  /** Sesión de entrenamiento cuyo instructivo se descarga. */
  trainingSessionId: number;
  /**
   * `false` si la sesión aún no tiene estructura de intervalos: deshabilita el
   * control (el servidor devolvería 404). Por defecto `true`.
   */
  hasStructure?: boolean;
  /**
   * Fecha de la sesión (`YYYY-MM-DD`) usada para nombrar el archivo descargado.
   * Si no se provee, se usa la fecha actual.
   */
  sessionDate?: string;
  className?: string;
}

/** Construye el nombre de archivo local: `instructivo_{marca}_{fecha}.pdf`. */
function buildFilename(brand: InstructivoBrand, sessionDate?: string): string {
  const date = (sessionDate ?? new Date().toISOString().slice(0, 10)).slice(0, 10);
  return `instructivo_${brand}_${date}.pdf`;
}

export function InstructivoDownloadButton({
  trainingSessionId,
  hasStructure = true,
  sessionDate,
  className,
}: InstructivoDownloadButtonProps): React.ReactElement {
  const [brand, setBrand] = React.useState<InstructivoBrand>("garmin");
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const download = useDownloadInstructivo();
  const isLoading = download.isPending;
  const disabled = !hasStructure || isLoading;

  const selectId = React.useId();
  const errorId = React.useId();

  const handleDownload = React.useCallback(() => {
    if (disabled) return;
    setErrorMessage(null);
    download.mutate(
      { trainingSessionId, brand },
      {
        onSuccess: (blob) => {
          triggerBlobDownload(blob, buildFilename(brand, sessionDate));
        },
        onError: (error) => {
          setErrorMessage(mapIntervalError(error).message);
        },
      },
    );
  }, [brand, disabled, download, sessionDate, trainingSessionId]);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label
            htmlFor={selectId}
            className="text-sm font-medium text-charcoal"
          >
            Dispositivo
          </label>
          <select
            id={selectId}
            value={brand}
            onChange={(event) => {
              setBrand(event.target.value as InstructivoBrand);
              setErrorMessage(null);
            }}
            disabled={disabled}
            className={cn(
              "min-h-11 rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 py-2",
              "text-sm text-charcoal transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {BRAND_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <Button
          type="button"
          variant="outline"
          onClick={handleDownload}
          disabled={disabled}
          aria-describedby={errorMessage ? errorId : undefined}
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="h-4 w-4" aria-hidden="true" />
          )}
          {isLoading ? "Generando…" : "Descargar instructivo"}
        </Button>
      </div>

      {!hasStructure ? (
        <p className="text-sm text-charcoal/70">
          Agregá una estructura de intervalos a la sesión para descargar el
          instructivo.
        </p>
      ) : null}

      {errorMessage ? (
        <p
          id={errorId}
          role="alert"
          className="flex items-center gap-1.5 text-sm text-red-600"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}

export default InstructivoDownloadButton;
