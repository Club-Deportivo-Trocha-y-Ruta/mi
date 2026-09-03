/**
 * PhotosGrid — "Fotos": miniaturas del mes (feature 038, T301). Solo
 * miniaturas + caption como alt text, nunca datos binarios ni metadatos
 * de otros deportistas (el backend ya filtra por consentimiento/etiqueta).
 */
import { Camera } from "lucide-react";

import type { PhotoView } from "@/types/stageLog.types";

export interface PhotosGridProps {
  photos: PhotoView[];
}

export function PhotosGrid({ photos }: PhotosGridProps) {
  if (photos.length === 0) return null;

  return (
    <section aria-label="Fotos" data-testid="photos-grid">
      <h3 className="font-display text-base font-semibold text-charcoal">Fotos</h3>
      <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
        {photos.map((photo, idx) => (
          <div
            key={photo.thumbnail_url}
            className="aspect-square overflow-hidden rounded-lg bg-light-gray"
          >
            {photo.thumbnail_url ? (
              <img
                src={photo.thumbnail_url}
                alt={photo.caption ?? `Foto ${idx + 1} del mes`}
                className="h-full w-full object-cover"
                loading="lazy"
              />
            ) : (
              <div
                className="flex h-full w-full items-center justify-center"
                role="img"
                aria-label={photo.caption ?? `Foto ${idx + 1} del mes`}
              >
                <Camera className="h-5 w-5 text-mid-gray" aria-hidden="true" />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
