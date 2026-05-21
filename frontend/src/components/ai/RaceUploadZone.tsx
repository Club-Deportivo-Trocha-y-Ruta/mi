/**
 * RaceUploadZone — drop zone simplificado para PDFs/CSVs Copa Valle.
 *
 * Diseño minimalista vs MediaUploadZone:
 *   - Sin chips de atletas / sin caption / sin consent (no aplican a PDFs).
 *   - Magic bytes pre-check cliente: lee primeros 5 bytes y valida `%PDF-`
 *     antes de aceptar (PDF). Para CSV valida UTF-8 + extensión.
 *   - Cap 8 MB cliente (env `VITE_RACE_MAX_PDF_MB`).
 *   - Accept configurable (resultados acepta PDF+CSV; general sólo PDF).
 *
 * A11y: el input file vive fuera del div role=button para evitar la
 * violación axe "nested-interactive". Sigue siendo accesible vía label
 * implícito (aria-label en el dropzone) + click→trigger del input oculto.
 */
import { useRef, useState } from "react";
import { FileText, Upload, X } from "lucide-react";

import { cn } from "@/lib/utils";

const DEFAULT_MAX_MB = Number(
  import.meta.env.VITE_RACE_MAX_PDF_MB ?? 8,
);

const PDF_MAGIC = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]); // "%PDF-"

export type RaceFileKind = "resultados" | "general";

interface RaceUploadZoneProps {
  /** Tipo de archivo: resultados (PDF/CSV) o general (sólo PDF). */
  kind: RaceFileKind;
  /** Etiqueta visible (ej: "Resultados *", "General (opcional)"). */
  label: string;
  /** Archivo seleccionado (null = idle). */
  value: File | null;
  /** Callback al aceptar archivo (post-validación) o limpiar (null). */
  onChange: (file: File | null) => void;
  /** Mensaje extra debajo del dropzone (ej: "obligatorio"). */
  hint?: string;
  /** Override del cap en MB (default 8). */
  maxMb?: number;
  /** Para testids externos. */
  "data-testid"?: string;
}

function acceptsForKind(kind: RaceFileKind): string {
  return kind === "resultados"
    ? "application/pdf,text/csv,.pdf,.csv"
    : "application/pdf,.pdf";
}

function isCsvLike(name: string): boolean {
  return /\.csv$/i.test(name);
}

async function validateMagicBytes(
  file: File,
  kind: RaceFileKind,
): Promise<string | null> {
  if (kind === "resultados" && isCsvLike(file.name)) {
    // Para CSV: verificar que primeros 256 bytes decodifiquen UTF-8.
    try {
      const slice = file.slice(0, 256);
      const buf = await slice.arrayBuffer();
      new TextDecoder("utf-8", { fatal: true }).decode(buf);
      return null;
    } catch {
      return "El archivo CSV no parece estar codificado en UTF-8.";
    }
  }
  // PDF: primeros 5 bytes deben ser "%PDF-".
  const slice = file.slice(0, 5);
  const buf = new Uint8Array(await slice.arrayBuffer());
  if (buf.length < 5) return "Archivo demasiado pequeño para ser PDF.";
  for (let i = 0; i < 5; i++) {
    if (buf[i] !== PDF_MAGIC[i]) {
      return "El archivo no es un PDF válido (cabecera %PDF- ausente).";
    }
  }
  return null;
}

export function RaceUploadZone({
  kind,
  label,
  value,
  onChange,
  hint,
  maxMb = DEFAULT_MAX_MB,
  "data-testid": dataTestId = `race-upload-${kind}`,
}: RaceUploadZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);

  const accept = acceptsForKind(kind);

  const validate = async (file: File): Promise<string | null> => {
    const lower = file.name.toLowerCase();
    const allowedExts =
      kind === "resultados" ? [".pdf", ".csv"] : [".pdf"];
    if (!allowedExts.some((ext) => lower.endsWith(ext))) {
      return `Formato no permitido. Permitidos: ${allowedExts.join(", ")}.`;
    }
    if (file.size > maxMb * 1024 * 1024) {
      return `Archivo excede el límite de ${maxMb} MB.`;
    }
    return await validateMagicBytes(file, kind);
  };

  const acceptFile = async (file: File) => {
    setValidating(true);
    setError(null);
    const err = await validate(file);
    setValidating(false);
    if (err) {
      setError(err);
      onChange(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    onChange(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void acceptFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) void acceptFile(file);
  };

  const reset = () => {
    setError(null);
    onChange(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="space-y-1" data-testid={dataTestId}>
      <p className="text-xs font-medium text-mid-gray">{label}</p>
      {!value ? (
        <div
          role="button"
          tabIndex={0}
          aria-label={`Soltar ${kind} aquí o presionar Enter para seleccionar`}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-light-gray px-4 py-5 transition-colors hover:border-mid-gray",
            error && "border-red-300",
          )}
          data-testid={`${dataTestId}-dropzone`}
        >
          <Upload size={18} className="text-mid-gray" aria-hidden="true" />
          <p className="mt-1.5 text-xs text-mid-gray">
            Arrastra archivo o haz clic
          </p>
          <p className="mt-0.5 text-[10px] text-mid-gray">
            {kind === "resultados" ? ".pdf .csv" : ".pdf"} · máx {maxMb} MB
          </p>
          {hint && (
            <p className="mt-0.5 text-[10px] italic text-mid-gray">{hint}</p>
          )}
        </div>
      ) : (
        <div
          className="flex items-center gap-2 rounded-xl bg-white px-3 py-2 ring-1 ring-light-gray"
          data-testid={`${dataTestId}-preview`}
        >
          <FileText size={16} className="text-mid-gray" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate text-sm text-charcoal">
            {value.name}
          </span>
          <span className="text-xs text-mid-gray">
            {(value.size / (1024 * 1024)).toFixed(2)} MB
          </span>
          <button
            type="button"
            onClick={reset}
            aria-label="Quitar archivo"
            className="rounded p-1 text-mid-gray hover:text-charcoal focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            data-testid={`${dataTestId}-remove`}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      )}
      {/* Input file fuera del dropzone para evitar nested-interactive (axe). */}
      {!value && (
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          className="hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={handleFileInput}
          data-testid={`${dataTestId}-input`}
        />
      )}
      {validating && (
        <p className="text-xs text-mid-gray">Validando archivo…</p>
      )}
      {error && (
        <p
          className="text-xs text-red-600"
          role="alert"
          data-testid={`${dataTestId}-error`}
        >
          {error}
        </p>
      )}
    </div>
  );
}
