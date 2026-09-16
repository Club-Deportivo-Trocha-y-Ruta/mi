/**
 * Tipos del módulo race-course (perfil de circuito de una válida).
 *
 * Mirror de los Pydantic schemas en `backend/app/schemas/race_course.py`
 * (feature 043). Contrato completo en
 * `specs/043-race-course-profile/contracts/course-api.md`.
 *
 * Endpoints cubiertos:
 *   - GET    /api/race-analysis/race-events/{id}/course
 *   - POST   /api/race-analysis/race-events/{id}/course/variants
 *   - PUT    /api/race-analysis/race-events/{id}/course/variants/{variant_id}/file
 *   - PATCH  /api/race-analysis/race-events/{id}/course/variants/{variant_id}
 *   - DELETE /api/race-analysis/race-events/{id}/course/variants/{variant_id}
 *   - PUT    /api/race-analysis/race-events/{id}/course/setups
 *   - PATCH  /api/race-analysis/race-events/{id}/course/description
 *
 * Privacidad: el GPX subido es la grabación personal del coach (una vuelta,
 * solo posición + elevación); el backend nunca persiste el archivo original
 * ni campos ajenos a la geometría (sin `<time>`, sin extensiones de FC/cadencia,
 * sin autor). Este módulo no contiene datos identificables de menores.
 */

// ---------------------------------------------------------------------------
// Catálogos de UI
// ---------------------------------------------------------------------------

/**
 * Tipo de terreno predominante del circuito.
 * Mirror de `TerrainType` enum del backend.
 */
export type TerrainType =
  | "sendero"
  | "trocha"
  | "mixto"
  | "pista"
  | "pavimento";

/**
 * Etiquetas en español para cada tipo de terreno.
 * Usar en <Select> del formulario de descripción del circuito.
 */
export const TERRAIN_TYPE_LABELS: Record<TerrainType, string> = {
  sendero: "Sendero",
  trocha: "Trocha",
  mixto: "Mixto",
  pista: "Pista",
  pavimento: "Pavimento",
};

/**
 * Sectores clave que puede tener un circuito (selección múltiple).
 * Mirror de `KeySector` enum del backend.
 */
export type KeySector =
  | "subida_larga"
  | "bajada_tecnica"
  | "rock_garden"
  | "singletrack"
  | "plano_rapido"
  | "paso_quebrada"
  | "raices"
  | "escalones";

/**
 * Etiquetas en español para cada sector clave.
 * Usar en checkboxes/chips del formulario de descripción del circuito.
 */
export const KEY_SECTOR_LABELS: Record<KeySector, string> = {
  subida_larga: "Subida larga",
  bajada_tecnica: "Bajada técnica",
  rock_garden: "Rock garden",
  singletrack: "Singletrack",
  plano_rapido: "Plano rápido",
  paso_quebrada: "Paso de quebrada",
  raices: "Raíces",
  escalones: "Escalones",
};

/**
 * Método de detección de vueltas al procesar el GPX subido.
 * - `closed_loop`: el track cierra sobre sí mismo N veces (detección automática).
 * - `manual`: el coach indicó `recorded_laps` explícitamente.
 * - `single`: no se detectó cierre; se asume una sola vuelta.
 */
export type DetectionMethod = "closed_loop" | "manual" | "single";

// ---------------------------------------------------------------------------
// GET /course — response completa
// ---------------------------------------------------------------------------

/**
 * Metadatos de cómo se determinó el número de vueltas de la grabación.
 */
export interface LapDetection {
  method: DetectionMethod;
  laps_detected: number;
  total_distance_m: number;
}

/**
 * Una variante de circuito (una grabación GPX procesada).
 * `geometry` es la polilínea de UNA vuelta: `[lat, lon, elevación|null]`.
 */
export interface CourseVariant {
  id: number;
  label: string;
  /** `lap_distance_m / 1000`, redondeado a 1 decimal. */
  lap_distance_km: number;
  lap_distance_m: number;
  /** `null` cuando `has_elevation` es `false` (GPX sin elevación). */
  elevation_gain_m: number | null;
  has_elevation: boolean;
  point_count: number;
  /** `[lat, lon, elevación|null]` — una vuelta completa. */
  geometry: Array<[number, number, number | null]>;
  detection: LapDetection;
  created_at: string; // ISO 8601 datetime
  updated_at: string | null; // ISO 8601 datetime
}

/**
 * Configuración de vueltas por categoría (tabla de "setups").
 */
export interface CourseSetup {
  category_id: number;
  category_code: string;
  category_label: string;
  laps: number;
  variant_id: number;
}

/**
 * Sugerencia de prellenado desde la válida anterior de la misma serie
 * (R-14). Solo presente cuando `setups` está vacío.
 */
export interface SuggestedSetup {
  category_id: number;
  category_label: string;
  laps: number;
  variant_label: string;
  source_event_id: number;
}

/**
 * Descripción cualitativa del circuito (los 4 campos editables vía PATCH).
 */
export interface CourseDescription {
  terrain_type: TerrainType | null;
  technical_difficulty: number | null; // 1..5 | null
  key_sectors: KeySector[];
  course_notes: string | null; // ≤ 1000 caracteres | null
}

/**
 * Categoría de un atleta del padre/madre que consulta — usado para resaltar
 * la fila correspondiente en la tabla de vueltas por categoría.
 * Sólo presente para el rol `parent`; `[]` para coach/admin.
 */
export interface MyCategory {
  athlete_id: number;
  category_id: number;
}

/**
 * Respuesta completa del circuito de una válida.
 * Devuelta por `GET /course` y por CADA mutación de este módulo (el backend
 * siempre retorna el `CourseRead` completo para que el cliente reemplace
 * la query key `["race-course", race_event_id]` en vez de mergear parciales).
 */
export interface CourseRead {
  race_event_id: number;
  /** `true` si hay al menos una variante O algún campo de `description`. */
  has_course_data: boolean;
  variants: CourseVariant[];
  setups: CourseSetup[];
  /** Sólo presente (no vacío) cuando `setups` está vacío; `[]` para parents. */
  suggested_setups: SuggestedSetup[];
  description: CourseDescription;
  /** `[]` para coach/admin; poblado sólo para el rol `parent`. */
  my_categories: MyCategory[];
}

// ---------------------------------------------------------------------------
// Bodies de escritura
// ---------------------------------------------------------------------------

/**
 * Un renglón de la tabla de vueltas por categoría.
 * Mirror de `SetupInput` del backend.
 */
export interface SetupInput {
  category_id: number;
  laps: number; // 1..20
  variant_id: number;
}

/**
 * Body de `PUT /course/setups` — reemplazo completo de la tabla.
 * Una lista vacía limpia la tabla.
 */
export interface SetupsReplaceBody {
  setups: SetupInput[];
}

/**
 * Body de `PATCH /course/variants/{id}` — solo permite renombrar.
 */
export interface VariantRenameBody {
  label: string; // 1..60 caracteres, trim
}

/**
 * Body de `PATCH /course/description` — todos los campos opcionales
 * (`exclude_unset` semántico: un campo ausente no se toca; `null` explícito
 * lo limpia), igual que `RaceEventConditionsUpdate`.
 */
export interface CourseDescriptionUpdateBody {
  terrain_type?: TerrainType | null;
  technical_difficulty?: number | null; // 1..5 | null
  key_sectors?: KeySector[] | null;
  course_notes?: string | null; // ≤ 1000 caracteres | null
}

/**
 * Payload de `POST /course/variants` (multipart).
 * `label` es requerido en la subida inicial.
 * `recorded_laps`, si se envía, fuerza `detection.method="manual"`.
 */
export interface VariantUploadPayload {
  file: File;
  label: string; // 1..60 caracteres, trim
  recorded_laps?: number; // 1..20
}

/**
 * Payload de `PUT /course/variants/{id}/file` (multipart).
 * No incluye `label` — el backend lo ignora en este endpoint (usar
 * `renameCourseVariant` para eso).
 */
export interface VariantReplacePayload {
  file: File;
  recorded_laps?: number; // 1..20
}

// ---------------------------------------------------------------------------
// Errores (contrato §6 — para JSDoc/manejo en el caller, no lanzados aquí)
// ---------------------------------------------------------------------------

/**
 * Códigos de error que puede devolver la API del circuito, en el shape
 * `{"detail": {"code": ..., "message": ...}}` (igual que el PATCH de
 * condiciones). Ver la tabla completa en
 * `specs/043-race-course-profile/contracts/course-api.md` §6.
 */
export type CourseErrorCode =
  | "unsupported_media_type" // 415
  | "not_gpx" // 422
  | "compressed_not_allowed" // 422
  | "xml_unsafe" // 422
  | "malformed" // 422
  | "no_track_points" // 422
  | "no_position" // 422
  | "too_short" // 422
  | "too_long" // 422
  | "too_few_points" // 422
  | "variant_not_in_event" // 422
  | "unknown_category" // 422
  | "duplicate_category" // 422
  | "file_too_large" // 413
  | "duplicate_recording" // 409
  | "variant_label_taken" // 409
  | "variant_in_use" // 409
  | "course_not_available" // 404
  | "race_event_not_found" // 404
  | "variant_not_found"; // 404
