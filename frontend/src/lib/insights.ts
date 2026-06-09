/**
 * Utilidades compartidas del módulo "Análisis IA" del atleta.
 *
 * Centraliza helpers de parsing de insights v2, etiquetas de enums
 * y calendario Copa Valle para que sean reutilizables desde
 * InsightsTimeline, HeroLastInsightCard y cualquier componente futuro
 * sin duplicación.
 *
 * Privacidad: ninguna de estas funciones maneja datos PII directamente;
 * el control de visibilidad (modo coach vs parent) se hace en los
 * componentes que consumen estas utilidades.
 */
import type { InsightConfidence } from "@/types/athleteRaceAnalysis.types";
import type { ProgressionAssessment } from "@/types/raceAnalysis.types";

export const PROMPT_VERSION_V2 = "race_analyst_v2";

// ---------------------------------------------------------------------------
// Parsing markdown v2
// ---------------------------------------------------------------------------

/** Normaliza acentos y casing para comparar headers tolerando variantes. */
function normalizeHeader(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/**
 * Extrae el contenido de una sección markdown delimitada por un header ##.
 * Devuelve el texto entre el header encontrado y el siguiente header ## (o
 * fin de string).
 *
 * Usa `startsWith` sobre el header normalizado para tolerar variantes del
 * backend (ej: "## Qué pasó en esta válida" matchea con headerText "Qué pasó").
 */
export function extractSection(markdown: string, headerText: string): string {
  const lines = markdown.split("\n");
  const needle = normalizeHeader(headerText);
  let inside = false;
  const collected: string[] = [];
  for (const line of lines) {
    if (/^##\s/.test(line)) {
      if (inside) break;
      const headerInLine = normalizeHeader(line.replace(/^##\s+/, ""));
      if (headerInLine.startsWith(needle)) {
        inside = true;
        continue;
      }
    } else if (inside) {
      collected.push(line);
    }
  }
  return collected.join("\n").trim();
}

/**
 * Extrae el contenido de la sección "## Contexto de temporada" cuando está
 * presente en el summary_text (insights v2 generados a partir de US-2 / FR-007).
 * Devuelve null cuando la sección no existe — así los insights legacy no se ven
 * afectados.
 */
export function extractSeasonContext(summaryText: string): string | null {
  const content = extractSection(summaryText, "Contexto de temporada");
  return content.length > 0 ? content : null;
}

/**
 * Mapa de ProgressionAssessment a etiquetas en español colombiano (es-CO).
 * Usado en la insignia de progresión del detalle del insight.
 */
export function progressionLabel(assessment: ProgressionAssessment): string {
  switch (assessment) {
    case "improving":
      return "Mejorando";
    case "stable":
      return "Estable";
    case "declining":
      return "En descenso";
    case "mixed":
      return "Mixto";
    case "first_reference":
      return "Primera referencia de la temporada";
  }
}

/**
 * Para la preview de la card, extrae la primera línea no vacía del bloque
 * "Qué pasó" en insights v2. Si no hay sección, devuelve el texto completo.
 */
export function getV2Preview(summaryText: string): string {
  const section = extractSection(summaryText, "Qué pasó");
  if (!section) return summaryText;
  const firstLine = section
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.length > 0);
  return firstLine ?? summaryText;
}

// ---------------------------------------------------------------------------
// Etiquetas de enums — reutilizables en lista y hero card
// ---------------------------------------------------------------------------

export function validaLabel(num: number | null | undefined): string {
  if (num === null || num === undefined) return "—";
  if (num === 0) return "Resumen de temporada";
  if (num === 99) return "Cto. Departamental";
  return `Válida ${num}`;
}

export function confidenceVariant(
  confidence: InsightConfidence,
): "success" | "warning" | "destructive" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "destructive";
}

export function confidenceLabel(confidence: InsightConfidence): string {
  if (confidence === "high") return "Confianza alta";
  if (confidence === "medium") return "Confianza media";
  return "Confianza baja";
}

// ---------------------------------------------------------------------------
// Calendario Copa Valle 2026 — tier por mes-año
// ---------------------------------------------------------------------------

/**
 * Mapa mes-año → tipo de carrera Copa Valle 2026.
 * Clave: "YYYY-MM" (ISO). Valores tomados del CLAUDE.md § Calendario Copa Valle 2026.
 *
 *   I   31-ene (2026-01)  → C  (sin tapering)
 *   II  28-feb (2026-02)  → C
 *   III 19-abr (2026-04)  → C  (diagnóstica)
 *   IV  17-may (2026-05)  → A  (tapering completo)
 *   CD  12-jun (2026-06)  → CD (Campeonato Departamental)
 *   V   01-ago (2026-08)  → B  (mini-tapering)
 *   VI  12-sep (2026-09)  → A
 *   VII 18-oct (2026-10)  → B
 */
const CARRERA_TIER: Record<string, "A" | "B" | "C" | "CD"> = {
  "2026-01": "C",
  "2026-02": "C",
  "2026-04": "C",
  "2026-05": "A",
  "2026-06": "CD",
  "2026-08": "B",
  "2026-09": "A",
  "2026-10": "B",
};

/**
 * Dado un insight (o su fecha ``generated_at``), devuelve el tier de la
 * carrera Copa Valle correspondiente al mes-año de la fecha.
 * Devuelve ``null`` si la fecha no coincide con ninguna válida del calendario.
 *
 * @param date - ISO date string o Date object (``generated_at`` del insight).
 */
export function getCarreraTier(
  date: Date | string,
): "A" | "B" | "C" | "CD" | null {
  const d = typeof date === "string" ? new Date(date) : date;
  if (!Number.isFinite(d.getTime())) return null;
  // getMonth() es 0-based — añadimos 1 y pad con "0".
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const year = String(d.getFullYear());
  const key = `${year}-${month}`;
  return CARRERA_TIER[key] ?? null;
}
