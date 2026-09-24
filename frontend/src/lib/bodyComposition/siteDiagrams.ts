/**
 * Especificación de diagramas por sitio de pliegue cutáneo (plicómetro).
 *
 * Fuente de verdad única para el texto en español ("Dónde" / "Cómo" /
 * alternativo accesible) que consumen tanto `SkinfoldSiteDiagram.tsx`
 * (ilustración `.webp` de `siteIllustrations.ts`) como el instructivo en
 * PDF (`backend/app/data/skinfold_sites.json`, feature 046 T056) — ambos
 * renderizadores deben leer estos mismos valores, nunca duplicarlos.
 *
 * Textos y técnica tomados de `docs/21-body-composition/research-protocol.md`
 * §1 (sitios y marcas anatómicas) y §2 (pellizco 1 cm por fuera de la marca,
 * plicómetro sobre la marca, lectura a los 2 segundos). Siempre lado derecho
 * ("D") por convención — no porque sea más preciso, sino por comparabilidad
 * en el tiempo y con las referencias poblacionales (FUPRECOL, Bogotá).
 */

export type SkinfoldSite =
  | "triceps"
  | "biceps"
  | "subscapular"
  | "medial_calf"
  | "iliac_crest"
  | "supraspinale";

export interface SkinfoldSiteDiagramSpec {
  /** Siempre "D" (derecho): convención ISAK usada por este protocolo. */
  sideTag: "D";
  /** Ubicación anatómica de la marca, en español, ≤ 3 líneas. */
  donde: string;
  /** Técnica de pellizco y lectura para ese sitio, en español, ≤ 3 líneas. */
  como: string;
  /** Texto alternativo accesible de la ilustración. */
  alt: string;
}

/** Orden canónico de captura (secuencia rotacional del asistente/wizard). */
export const SKINFOLD_SITE_ORDER: readonly SkinfoldSite[] = [
  "triceps",
  "biceps",
  "subscapular",
  "medial_calf",
  "iliac_crest",
  "supraspinale",
];

const TECNICA_LECTURA =
  "Pellizca el pliegue firmemente 1 cm por fuera de la marca; coloca el plicómetro sobre la marca y lee a los 2 segundos de soltar la presión.";

export const SKINFOLD_SITE_DIAGRAMS: Record<SkinfoldSite, SkinfoldSiteDiagramSpec> = {
  triceps: {
    sideTag: "D",
    donde:
      "Cara posterior del brazo derecho, a la mitad entre el hombro (acromion) y el codo (olécranon), con el brazo relajado al costado.",
    como: TECNICA_LECTURA,
    alt: "Diagrama del pliegue de tríceps: brazo derecho visto por detrás, marca a la mitad entre el hombro y el codo, pliegue vertical.",
  },
  biceps: {
    sideTag: "D",
    donde:
      "Cara anterior del brazo derecho, a la misma altura que la marca del tríceps, con el brazo relajado al costado.",
    como: TECNICA_LECTURA,
    alt: "Diagrama del pliegue de bíceps: brazo derecho visto por delante, marca a la altura del tríceps, pliegue vertical.",
  },
  subscapular: {
    sideTag: "D",
    donde:
      "Justo debajo del ángulo inferior del omóplato derecho, ubicado por palpación con el brazo relajado.",
    como:
      "Pellizca el pliegue en diagonal hacia abajo y hacia afuera (~45°), 1 cm por fuera de la marca; lee a los 2 segundos.",
    alt: "Diagrama del pliegue subescapular: espalda derecha, marca bajo el ángulo del omóplato, pliegue diagonal hacia afuera.",
  },
  medial_calf: {
    sideTag: "D",
    donde:
      "Borde medial de la pantorrilla derecha, en el punto de mayor perímetro, con la rodilla flexionada 90° y la pantorrilla relajada.",
    como: TECNICA_LECTURA,
    alt: "Diagrama del pliegue de pantorrilla medial: pierna derecha, marca en el punto de mayor perímetro, pliegue vertical.",
  },
  iliac_crest: {
    sideTag: "D",
    donde:
      "Sobre el punto más lateral de la cresta ilíaca derecha (iliocristale), en la línea media de la axila.",
    como:
      "Pellizca el pliegue casi horizontal, con una leve inclinación hacia abajo, 1 cm por fuera de la marca; coloca el plicómetro sobre la marca y lee a los 2 segundos.",
    alt: "Diagrama del pliegue ilíaco: cadera derecha, marca lateral sobre la cresta ilíaca en la línea axilar media, pliegue casi horizontal.",
  },
  supraspinale: {
    sideTag: "D",
    donde:
      "Sobre la línea que va desde la espina ilíaca anterosuperior derecha hasta el borde anterior de la axila, unos 5 a 7 cm por encima de esa espina.",
    como:
      "Pellizca el pliegue en diagonal, hacia abajo y hacia adentro, en dirección a la ingle, 1 cm por fuera de la marca; lee a los 2 segundos.",
    alt: "Diagrama del pliegue supraespinal: cadera derecha, marca más arriba y hacia el centro que la cresta ilíaca, pliegue oblicuo hacia adentro.",
  },
};

export function getSkinfoldSiteDiagram(site: SkinfoldSite): SkinfoldSiteDiagramSpec {
  return SKINFOLD_SITE_DIAGRAMS[site];
}
