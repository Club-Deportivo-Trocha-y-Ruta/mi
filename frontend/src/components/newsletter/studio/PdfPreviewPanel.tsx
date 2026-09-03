/**
 * PdfPreviewPanel — panel de descarga del PDF en el estudio de la bitácora
 * (feature 038, T302). Reemplaza a `DevicePreview`: el coach ya no
 * previsualiza Móvil/Correo dentro de la app — solo necesita generar y
 * abrir el PDF, que es el artefacto real que ve y comparte.
 */
import { Download, FileText } from "lucide-react";

export interface PdfPreviewPanelProps {
  onDownloadPdf: () => void;
  isDownloadingPdf?: boolean;
  canDownloadPdf?: boolean;
}

export function PdfPreviewPanel({
  onDownloadPdf,
  isDownloadingPdf = false,
  canDownloadPdf = true,
}: PdfPreviewPanelProps) {
  return (
    <div
      data-testid="pdf-preview-panel"
      className="flex h-96 flex-col items-center justify-center gap-3 rounded-xl bg-light-gray text-center"
    >
      <FileText className="h-8 w-8 text-mid-gray" aria-hidden="true" />
      <p className="max-w-xs text-sm text-mid-gray">
        El PDF se genera con el mismo contenido de la bitácora, en hasta 3
        páginas.
      </p>
      <button
        type="button"
        onClick={onDownloadPdf}
        disabled={!canDownloadPdf || isDownloadingPdf}
        className="flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        data-testid="pdf-preview-download-pdf"
      >
        <Download className="h-4 w-4" aria-hidden="true" />
        {isDownloadingPdf ? "Generando…" : "Descargar PDF"}
      </button>
    </div>
  );
}
