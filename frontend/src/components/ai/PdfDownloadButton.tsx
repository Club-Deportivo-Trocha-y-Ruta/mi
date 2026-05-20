/**
 * Botón de descarga PDF del análisis (race-analysis §10.2).
 *
 * Disabled hasta que el run esté `done`. Usa `downloadRunPdf` que
 * adjunta el JWT manualmente y dispara la descarga vía blob URL.
 */
import { useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { downloadRunPdf } from "@/api/raceAnalysis";
import { useAuthStore } from "@/store/auth.store";
import { cn } from "@/lib/utils";

interface PdfDownloadButtonProps {
  runId: string;
  /** Habilitar el botón sólo cuando el run terminó. */
  enabled: boolean;
  className?: string;
}

export function PdfDownloadButton({
  runId,
  enabled,
  className,
}: PdfDownloadButtonProps) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setError(null);
    setIsDownloading(true);
    try {
      await downloadRunPdf(runId, accessToken);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo descargar el PDF.",
      );
    } finally {
      setIsDownloading(false);
    }
  };

  const disabled = !enabled || isDownloading;

  return (
    <div className={cn("inline-flex flex-col gap-1", className)}>
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        aria-label="Descargar análisis en PDF"
        data-testid="pdf-download-button"
        className={cn(
          "inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity",
          disabled
            ? "opacity-50 cursor-not-allowed"
            : "hover:opacity-90",
        )}
      >
        {isDownloading ? (
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        ) : (
          <Download size={16} aria-hidden="true" />
        )}
        {isDownloading ? "Descargando..." : "Descargar PDF"}
      </button>
      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
