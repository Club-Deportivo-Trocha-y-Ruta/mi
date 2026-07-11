import { useId, useRef } from "react";
import { FileUp, X } from "lucide-react";

interface RouteFileDropzoneProps {
  value: File | null;
  onChange: (file: File | null) => void;
  /** Error de subida posterior al guardado (no bloquea la sesión ya creada). */
  error?: string | null;
}

const ACCEPT = ".gpx,.fit";
const MAX_MB = 5;

/**
 * Selector de archivo de recorrido (.gpx/.fit) usado dentro del formulario.
 * El archivo se mantiene en estado del componente (no en RHF) y se sube al
 * endpoint existente inmediatamente después de crear la sesión.
 */
export function RouteFileDropzone({ value, onChange, error }: RouteFileDropzoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);

  function handleFile(file: File | null) {
    if (!file) {
      onChange(null);
      return;
    }
    const name = file.name.toLowerCase();
    if (!name.endsWith(".gpx") && !name.endsWith(".fit")) {
      // Validación de cortesía en cliente; el servidor valida por magic bytes.
      onChange(null);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    onChange(file);
  }

  return (
    <div className="space-y-1">
      <label htmlFor={inputId} className="block text-sm font-medium text-charcoal">
        Archivo de recorrido{" "}
        <span className="font-normal text-mid-gray">(opcional, .gpx o .fit)</span>
      </label>

      {value ? (
        <div className="flex min-h-[48px] items-center justify-between rounded-lg bg-white px-3 py-2 shadow-ring">
          <span className="truncate text-sm text-charcoal" data-testid="route-file-name">
            {value.name}
          </span>
          <button
            type="button"
            onClick={() => {
              onChange(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full text-mid-gray hover:bg-light-gray"
            aria-label="Quitar archivo de recorrido"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          className="flex min-h-[48px] cursor-pointer items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm text-mid-gray transition-colors hover:bg-light-gray shadow-ring"
        >
          <FileUp size={16} aria-hidden="true" />
          Seleccionar archivo (.gpx / .fit, máx. {MAX_MB} MB)
        </label>
      )}

      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
      />

      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
