import { useRef, useState } from "react";
import { AlertTriangle, Image as ImageIcon, Loader2, Upload, Video } from "lucide-react";

import type {
  MediaType,
  SessionMediaUploadPayload,
} from "@/types/trainingSession.types";

const PHOTO_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const VIDEO_EXTENSIONS = [".mp4", ".mov"];
const MAX_PHOTO_MB = 10;
const MAX_VIDEO_MB = 50;

interface AthleteOption {
  id: number;
  label: string;
}

interface MediaUploadZoneProps {
  athletes: AthleteOption[];
  onUpload: (payload: SessionMediaUploadPayload) => Promise<unknown>;
  isUploading?: boolean;
  uploadError?: string | null;
}

function detectMediaType(filename: string): MediaType | null {
  const lower = filename.toLowerCase();
  if (PHOTO_EXTENSIONS.some((ext) => lower.endsWith(ext))) return "photo";
  if (VIDEO_EXTENSIONS.some((ext) => lower.endsWith(ext))) return "video";
  return null;
}

export function MediaUploadZone({
  athletes,
  onUpload,
  isUploading = false,
  uploadError = null,
}: MediaUploadZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [selectedAthletes, setSelectedAthletes] = useState<number[]>([]);
  const [consentAck, setConsentAck] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const reset = () => {
    setPendingFile(null);
    setCaption("");
    setSelectedAthletes([]);
    setConsentAck(false);
    setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const validate = (file: File): string | null => {
    const type = detectMediaType(file.name);
    if (!type) {
      return `Formato no permitido. Fotos: ${PHOTO_EXTENSIONS.join(", ")}, videos: ${VIDEO_EXTENSIONS.join(", ")}.`;
    }
    const maxMb = type === "photo" ? MAX_PHOTO_MB : MAX_VIDEO_MB;
    if (file.size > maxMb * 1024 * 1024) {
      return `Archivo excede el límite de ${maxMb} MB para ${type === "photo" ? "fotos" : "videos"}.`;
    }
    return null;
  };

  const acceptFile = (file: File) => {
    const err = validate(file);
    if (err) {
      setValidationError(err);
      setPendingFile(null);
      return;
    }
    setValidationError(null);
    setPendingFile(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) acceptFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) acceptFile(file);
  };

  const toggleAthlete = (athleteId: number) => {
    setSelectedAthletes((prev) =>
      prev.includes(athleteId)
        ? prev.filter((id) => id !== athleteId)
        : [...prev, athleteId],
    );
  };

  const canSubmit =
    pendingFile !== null &&
    selectedAthletes.length > 0 &&
    consentAck &&
    !isUploading;

  const handleSubmit = async () => {
    if (!pendingFile) return;
    const mediaType = detectMediaType(pendingFile.name);
    if (!mediaType) return;
    try {
      await onUpload({
        file: pendingFile,
        media_type: mediaType,
        athlete_ids: selectedAthletes,
        consent_ack: consentAck,
        caption: caption.trim() || undefined,
      });
      reset();
    } catch {
      // El padre maneja el error vía `uploadError`
    }
  };

  return (
    <div className="space-y-3" data-testid="media-upload-zone">
      {!pendingFile ? (
        <div
          role="button"
          tabIndex={0}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onClick={() => fileInputRef.current?.click()}
          aria-label="Soltar foto/video aquí o presionar Enter para seleccionar"
          className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-light-gray px-4 py-6 transition-colors hover:border-mid-gray"
          data-testid="media-upload-dropzone"
        >
          <Upload size={20} className="text-mid-gray" aria-hidden="true" />
          <p className="mt-2 text-sm text-mid-gray">
            Arrastra foto (.jpg/.png/.webp ≤ {MAX_PHOTO_MB} MB) o video (.mp4/.mov ≤ {MAX_VIDEO_MB} MB)
          </p>
          <p className="mt-1 text-xs text-mid-gray">o haz clic para seleccionar</p>
          <input
            ref={fileInputRef}
            type="file"
            accept={[...PHOTO_EXTENSIONS, ...VIDEO_EXTENSIONS].join(",")}
            className="hidden"
            onChange={handleFileInput}
            data-testid="media-file-input"
            aria-label="Subir archivo de foto o video"
          />
        </div>
      ) : (
        <div
          className="rounded-xl border border-light-gray p-4 space-y-3"
          data-testid="media-upload-form"
        >
          <div className="flex items-center gap-2 text-sm">
            {detectMediaType(pendingFile.name) === "photo" ? (
              <ImageIcon size={16} className="text-mid-gray" aria-hidden="true" />
            ) : (
              <Video size={16} className="text-mid-gray" aria-hidden="true" />
            )}
            <span className="font-medium text-charcoal">{pendingFile.name}</span>
            <span className="text-mid-gray">
              ({(pendingFile.size / (1024 * 1024)).toFixed(1)} MB)
            </span>
            <button
              type="button"
              onClick={reset}
              className="ml-auto text-xs text-mid-gray underline hover:opacity-70"
              aria-label="Quitar archivo seleccionado"
            >
              Quitar
            </button>
          </div>

          <div>
            <label htmlFor="media-caption" className="block text-xs text-mid-gray">
              Pie de foto (opcional, máx. 280 caracteres)
            </label>
            <input
              id="media-caption"
              type="text"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              maxLength={280}
              placeholder="Ej: técnica de descenso en sección rocosa"
              className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none focus:ring-2 focus:ring-blue-500/40"
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            />
          </div>

          <fieldset>
            <legend className="block text-xs text-mid-gray">
              Atletas que aparecen (al menos 1) — sólo los padres de estos atletas verán la media
            </legend>
            <div
              className="mt-2 flex flex-wrap gap-1.5"
              data-testid="media-athlete-chips"
            >
              {athletes.length === 0 ? (
                <p className="text-xs text-mid-gray">
                  Esta sesión no tiene atletas convocados.
                </p>
              ) : (
                athletes.map((a) => {
                  const active = selectedAthletes.includes(a.id);
                  return (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => toggleAthlete(a.id)}
                      className={`rounded-full px-3 py-1 text-xs font-medium transition-opacity ${
                        active
                          ? "bg-charcoal text-white"
                          : "bg-light-gray text-charcoal"
                      }`}
                      aria-pressed={active}
                    >
                      {a.label}
                    </button>
                  );
                })
              )}
            </div>
          </fieldset>

          <div
            className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900"
            role="region"
            aria-label="Aviso legal de consentimiento"
          >
            <p className="flex items-start gap-1.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>
                Sólo sube material de atletas con consentimiento parental
                documentado (Ley 1581 Colombia + Ley 1098). Strippeamos GPS de
                fotos antes de almacenar.
              </span>
            </p>
            <label className="mt-2 flex items-center gap-2">
              <input
                type="checkbox"
                checked={consentAck}
                onChange={(e) => setConsentAck(e.target.checked)}
                data-testid="media-consent-checkbox"
              />
              <span className="font-medium">
                Confirmo tener consentimiento parental para los atletas etiquetados.
              </span>
            </label>
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            data-testid="media-submit-button"
          >
            {isUploading && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Subir media
          </button>
        </div>
      )}

      {(validationError || uploadError) && (
        <p className="text-sm text-red-600" role="alert">
          {validationError ?? uploadError}
        </p>
      )}
    </div>
  );
}
