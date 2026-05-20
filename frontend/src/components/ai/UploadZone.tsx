/**
 * UploadZone para PDFs/CSVs de resultados Copa Valle (race-analysis §10.2 #UploadZone).
 *
 * Drag-drop + click-to-pick. Validación tipo/tamaño en cliente. NO
 * confunde con `components/training/MediaUploadZone.tsx` — aquel es
 * para fotos/videos de sesiones, este es para PDFs/CSVs de carreras.
 *
 * NOTA: `react-dropzone` no está instalado en el proyecto (verificado
 * 2026-05-20). Implementación con input nativo + drag handlers.
 *
 * Privacidad: el contenido del PDF lo procesa el backend; aquí sólo
 * validamos formato.
 */
import { useRef, useState } from "react";
import { FileText, Loader2, Upload } from "lucide-react";

import { cn } from "@/lib/utils";

const ALLOWED_EXTENSIONS = [".pdf", ".csv"] as const;
const ALLOWED_MIMES = [
  "application/pdf",
  "text/csv",
  "application/vnd.ms-excel", // algunos clientes envían csv con este mime
] as const;
const MAX_MB = 10;

export interface UploadZoneProps {
  onUpload: (file: File) => Promise<unknown> | void;
  /** Forzado externamente para mostrar spinner cuando la mutation está en vuelo. */
  isUploading?: boolean;
  /** Mensaje de error externo (servidor). El UploadZone también muestra errores propios de validación. */
  uploadError?: string | null;
  /** Override mb-max para tests. */
  maxMb?: number;
  /** Override extensiones para tests. */
  accept?: readonly string[];
}

function detectKind(file: File): "pdf" | "csv" | null {
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".pdf") || file.type === "application/pdf") return "pdf";
  if (lower.endsWith(".csv") || file.type === "text/csv") return "csv";
  return null;
}

export function UploadZone({
  onUpload,
  isUploading = false,
  uploadError = null,
  maxMb = MAX_MB,
  accept = ALLOWED_EXTENSIONS,
}: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const validate = (file: File): string | null => {
    if (!detectKind(file)) {
      const mimeOk = ALLOWED_MIMES.includes(file.type as never);
      if (!mimeOk) {
        return `Formato no permitido. Acepta: ${accept.join(", ")}.`;
      }
    }
    const sizeMb = file.size / (1024 * 1024);
    if (sizeMb > maxMb) {
      return `Archivo excede el límite de ${maxMb} MB (${sizeMb.toFixed(1)} MB).`;
    }
    return null;
  };

  const handleFile = async (file: File) => {
    const err = validate(file);
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError(null);
    try {
      await onUpload(file);
      if (inputRef.current) inputRef.current.value = "";
    } catch {
      // El padre muestra error via prop `uploadError`.
    }
  };

  const onInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) await handleFile(f);
  };

  const onDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) await handleFile(f);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  const error = validationError ?? uploadError;

  return (
    <div className="space-y-2" data-testid="upload-zone">
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={onKeyDown}
        onDrop={onDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        aria-label="Arrastra un PDF o CSV o presiona Enter para seleccionar"
        aria-describedby="upload-zone-hint"
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 transition-colors",
          isDragging
            ? "border-charcoal bg-light-gray/30"
            : "border-light-gray hover:border-mid-gray",
          isUploading && "opacity-60 pointer-events-none",
        )}
        data-testid="upload-zone-dropzone"
      >
        {isUploading ? (
          <Loader2
            size={24}
            className="animate-spin text-mid-gray"
            aria-hidden="true"
          />
        ) : (
          <Upload size={24} className="text-mid-gray" aria-hidden="true" />
        )}
        <p className="mt-2 text-sm font-medium text-charcoal">
          {isUploading ? "Subiendo..." : "Arrastra un PDF o CSV"}
        </p>
        <p id="upload-zone-hint" className="mt-1 text-xs text-mid-gray">
          o haz clic para seleccionar — máx {maxMb} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={[...accept].join(",")}
          onChange={onInputChange}
          className="hidden"
          data-testid="upload-zone-input"
          aria-label="Seleccionar archivo PDF o CSV"
        />
      </div>

      {error && (
        <p className="flex items-center gap-1 text-sm text-red-600" role="alert">
          <FileText size={14} aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
}
