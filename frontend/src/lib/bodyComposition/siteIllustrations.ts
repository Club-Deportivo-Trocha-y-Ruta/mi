/**
 * Ilustraciones por sitio de pliegue cutáneo (feature 046).
 *
 * Los `.webp` viven en `src/assets/skinfolds/{sitio}.webp` (cuadrados de
 * 768×768, fondo blanco, sin texto dentro de la imagen — los rótulos se
 * superponen como HTML accesible). Se importan de forma estática, una por
 * sitio: si un archivo falta, el build de Vite falla en lugar de dejar un
 * hueco silencioso en el instructivo.
 *
 * Los textos ("Dónde", "Cómo", alt accesible) siguen viviendo en
 * `siteDiagrams.ts`; este archivo sólo aporta la imagen.
 */
import bicepsUrl from "@/assets/skinfolds/biceps.webp";
import iliacCrestUrl from "@/assets/skinfolds/iliac_crest.webp";
import medialCalfUrl from "@/assets/skinfolds/medial_calf.webp";
import subscapularUrl from "@/assets/skinfolds/subscapular.webp";
import supraspinaleUrl from "@/assets/skinfolds/supraspinale.webp";
import tricepsUrl from "@/assets/skinfolds/triceps.webp";

import type { SkinfoldSite } from "./siteDiagrams";

/** Lado (px) intrínseco de las ilustraciones; reserva el espacio sin saltos de layout. */
export const SITE_ILLUSTRATION_SIZE = 768;

const SITE_ILLUSTRATIONS: Record<SkinfoldSite, string> = {
  triceps: tricepsUrl,
  biceps: bicepsUrl,
  subscapular: subscapularUrl,
  medial_calf: medialCalfUrl,
  iliac_crest: iliacCrestUrl,
  supraspinale: supraspinaleUrl,
};

/** URL de la ilustración del sitio. */
export function getSiteIllustration(site: SkinfoldSite): string {
  return SITE_ILLUSTRATIONS[site];
}
