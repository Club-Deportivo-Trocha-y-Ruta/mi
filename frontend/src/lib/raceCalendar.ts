/**
 * Calendario Copa Valle 2026 — mapeo de válidas a tipo de carrera + metadata.
 *
 * Fuente única de verdad para el "tipo" de carrera (A/B/C/CD) usado por el
 * Comparador v2 para mostrar el chip de carrera + warning de tapering.
 *
 * Tipos:
 *   - A  → Pico (tapering completo 5-7d).
 *   - B  → Importante (mini-tapering 3-4d).
 *   - C  → Diagnóstica (sin tapering).
 *   - CD → Campeonato Departamental.
 *
 * Calendario literal de CLAUDE.md (no editar sin alinear con el coach).
 */
export type RaceType = "A" | "B" | "C" | "CD";
export type TaperingLevel = "5-7d" | "3-4d" | "sin";

export interface RaceMeta {
  /** Tipo de carrera del plan periodizado. */
  type: RaceType;
  /** Nombre corto, usualmente la ubicación. */
  label: string;
  /** Indicador del tapering aplicado a esa válida. */
  tapering: TaperingLevel;
  /** Fecha en formato ISO ``YYYY-MM-DD``. */
  date_iso: string;
  /** Ubicación / ciudad sede. */
  location: string;
}

/**
 * Mapa por ``valida_num``. La key 99 corresponde al Campeonato Departamental,
 * convención usada en todo el módulo race-results v2.
 */
export const RACE_CALENDAR_2026: Readonly<Record<number, RaceMeta>> = {
  1: {
    type: "C",
    label: "Sevilla",
    tapering: "sin",
    date_iso: "2026-01-31",
    location: "Sevilla",
  },
  2: {
    type: "C",
    label: "Ginebra",
    tapering: "sin",
    date_iso: "2026-02-28",
    location: "Ginebra",
  },
  3: {
    type: "C",
    label: "La Cumbre",
    tapering: "sin",
    date_iso: "2026-04-19",
    location: "La Cumbre",
  },
  4: {
    type: "A",
    label: "Cali",
    tapering: "5-7d",
    date_iso: "2026-05-17",
    location: "Cali",
  },
  99: {
    type: "CD",
    label: "Cto. Departamental",
    tapering: "5-7d",
    date_iso: "2026-06-26",
    location: "Ginebra",
  },
  5: {
    type: "B",
    label: "Palmira",
    tapering: "3-4d",
    date_iso: "2026-08-01",
    location: "Palmira",
  },
  6: {
    type: "A",
    label: "Roldanillo",
    tapering: "5-7d",
    date_iso: "2026-09-12",
    location: "Roldanillo",
  },
  7: {
    type: "B",
    label: "Yumbo",
    tapering: "3-4d",
    date_iso: "2026-10-18",
    location: "Yumbo",
  },
};

/**
 * Devuelve metadata de la válida o ``null`` si la combinación no es conocida.
 *
 * Solo soporta la temporada 2026 hoy. Para futuras temporadas habrá que
 * sumar mapas dedicados — preferimos devolver ``null`` y que la UI degrade
 * elegante a no contradecir el plan periodizado.
 */
export function getRaceMeta(
  season: number,
  validaNum: number | null | undefined,
): RaceMeta | null {
  if (season !== 2026) return null;
  if (validaNum === null || validaNum === undefined) return null;
  return RACE_CALENDAR_2026[validaNum] ?? null;
}

export interface RaceTypeBadgeStyle {
  /** Clases Tailwind para fondo + texto WCAG AA. */
  className: string;
  /** Etiqueta corta usada en el chip. */
  label: string;
}

/**
 * Estilos por tipo de carrera. Tonos -100/-800 para asegurar contraste
 * AA incluso bajo sol fuerte (uso tablet en pista).
 */
export function getRaceTypeBadgeStyle(type: RaceType): RaceTypeBadgeStyle {
  switch (type) {
    case "A":
      return {
        className: "bg-red-100 text-red-800",
        label: "Tipo A · Pico",
      };
    case "B":
      return {
        className: "bg-orange-100 text-orange-800",
        label: "Tipo B · Importante",
      };
    case "C":
      return {
        className: "bg-blue-100 text-blue-800",
        label: "Tipo C · Diagnóstica",
      };
    case "CD":
      return {
        className: "bg-purple-100 text-purple-800",
        label: "Cto. Departamental",
      };
  }
}

/**
 * Etiqueta legible "Válida III", "Cto. Departamental", etc.
 */
export function getValidaLabel(validaNum: number | null | undefined): string {
  if (validaNum === null || validaNum === undefined) return "—";
  if (validaNum === 99) return "Cto. Departamental";
  const romans: Record<number, string> = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
    6: "VI",
    7: "VII",
  };
  return `Válida ${romans[validaNum] ?? validaNum}`;
}
