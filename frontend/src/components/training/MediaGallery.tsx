import { useState } from "react";
import { Loader2, Trash2, X } from "lucide-react";

import type {
  SessionMedia,
  SessionMediaParent,
} from "@/types/trainingSession.types";

interface MediaGalleryProps {
  media: Array<SessionMedia | SessionMediaParent>;
  readOnly?: boolean;
  onDelete?: (mediaId: number) => void;
  isDeleting?: boolean;
}

function isCoachMedia(m: SessionMedia | SessionMediaParent): m is SessionMedia {
  return "athlete_ids" in m;
}

export function MediaGallery({
  media,
  readOnly = false,
  onDelete,
  isDeleting = false,
}: MediaGalleryProps) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  if (media.length === 0) {
    return (
      <p className="text-sm text-mid-gray" data-testid="media-gallery-empty">
        Aún no hay fotos ni videos para esta sesión.
      </p>
    );
  }

  const active = activeIdx !== null ? media[activeIdx] : null;

  return (
    <>
      <div
        className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4"
        data-testid="media-gallery-grid"
      >
        {media.map((item, idx) => {
          const isVideo = item.media_type === "video";
          const thumb = item.thumbnail_url ?? (isVideo ? null : item.storage_url);
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActiveIdx(idx)}
              className="group relative aspect-square overflow-hidden rounded-lg bg-light-gray transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
              aria-label={
                isVideo
                  ? `Ver video subido el ${item.uploaded_at}`
                  : `Ver foto subida el ${item.uploaded_at}`
              }
              data-testid={`media-thumb-${item.id}`}
            >
              {thumb ? (
                <img
                  src={thumb}
                  alt={item.caption ?? ""}
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-charcoal/80 text-xs font-medium text-white">
                  ▶ Video
                </div>
              )}
              {isVideo && (
                <span
                  className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white"
                  aria-hidden="true"
                >
                  Video
                </span>
              )}
            </button>
          );
        })}
      </div>

      {active && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Vista ampliada de la media"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setActiveIdx(null)}
          data-testid="media-lightbox"
        >
          <div
            className="relative max-h-full max-w-3xl w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setActiveIdx(null)}
              className="absolute -top-10 right-0 rounded-full bg-white/10 p-1.5 text-white hover:bg-white/20"
              aria-label="Cerrar"
            >
              <X size={18} aria-hidden="true" />
            </button>

            {active.media_type === "photo" ? (
              <img
                src={active.storage_url}
                alt={active.caption ?? ""}
                className="mx-auto max-h-[80vh] rounded-lg"
              />
            ) : (
              <video
                src={active.storage_url}
                controls
                preload="metadata"
                className="mx-auto max-h-[80vh] w-full rounded-lg"
                data-testid="media-video-player"
              />
            )}

            {active.caption && (
              <p className="mt-3 text-center text-sm text-white">{active.caption}</p>
            )}

            {!readOnly && isCoachMedia(active) && onDelete && (
              <div className="mt-3 flex justify-center">
                <button
                  type="button"
                  onClick={() => {
                    if (
                      window.confirm(
                        "¿Borrar esta media? Se eliminará para padres y entrenador.",
                      )
                    ) {
                      onDelete(active.id);
                      setActiveIdx(null);
                    }
                  }}
                  disabled={isDeleting}
                  className="flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                  data-testid="media-delete-button"
                >
                  {isDeleting ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 size={14} aria-hidden="true" />
                  )}
                  Borrar
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
