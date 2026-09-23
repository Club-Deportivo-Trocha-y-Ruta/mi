/**
 * CourseDescriptionCard — tarjeta tri-estado para la descripción cualitativa
 * del circuito de una válida (feature 043, US3).
 *
 * Estados (sobre 4 campos posibles: terrain_type, technical_difficulty,
 * key_sectors no vacío, course_notes no vacío):
 *  - Vacío (0/4): card colapsada + botón "Describir la pista" (coach/admin).
 *    Para el rol parent en este estado no se renderiza nada — no tiene
 *    sentido mostrarle un CTA de edición que no puede usar.
 *  - Parcial (1-3/4): card con lo registrado + botón "Completar".
 *  - Completo (4/4): card normal con los 4 campos + botón secundario "Editar".
 *
 * Diseño: copia estructural y de clases Tailwind de
 * `components/race/RaceConditionsCard.tsx` (mismo patrón tri-estado, mismo
 * `ConditionRow`/`EmptyPlaceholder` inline ya que esos helpers no se exportan
 * desde el archivo original).
 *
 * `readOnly` (rol parent, vía prop explícita — igual que `VariantsCard` y
 * `CategorySetupTable` de este mismo módulo, sin chequeo de rol propio):
 *  - Sin botón de edición.
 *  - Solo se muestran las filas de campos que sí tienen valor — sin
 *    placeholders "— sin registro —" para lo que el coach no llenó, ya que
 *    esa señal es para el coach, no para la familia.
 *
 * El sheet de edición (EditCourseDescriptionDialog) se monta lazy para no
 * impactar el chunk de la pestaña Circuito.
 */
import { lazy, Suspense, useState } from "react";

import {
  KEY_SECTOR_LABELS,
  TERRAIN_TYPE_LABELS,
} from "@/types/raceCourse.types";
import type { CourseDescription, KeySector, TerrainType } from "@/types/raceCourse.types";

const EditCourseDescriptionDialog = lazy(() =>
  import("@/components/race/course/EditCourseDescriptionDialog").then((m) => ({
    default: m.EditCourseDescriptionDialog,
  })),
);

// ---------------------------------------------------------------------------
// Catálogos locales de UI
// ---------------------------------------------------------------------------

/** Mismas etiquetas que `EditCourseDescriptionDialog` (no exportadas desde
 * ahí — se duplican aquí, igual que el resto de este patrón tri-estado). */
const DIFFICULTY_LABELS: Record<number, string> = {
  1: "1 — Muy fácil",
  2: "2 — Fácil",
  3: "3 — Media",
  4: "4 — Técnico",
  5: "5 — Muy técnico",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Cuenta cuántos de los 4 campos de descripción están rellenos. */
function countFilledFields(d: Partial<CourseDescription>): number {
  let n = 0;
  if (d.terrain_type != null) n++;
  if (d.technical_difficulty != null) n++;
  if (d.key_sectors && d.key_sectors.length > 0) n++;
  if (d.course_notes && d.course_notes.trim() !== "") n++;
  return n;
}

function formatTerrain(v: TerrainType | null | undefined): string {
  if (v == null) return "";
  return TERRAIN_TYPE_LABELS[v] ?? v;
}

function formatDifficulty(v: number | null | undefined): string {
  if (v == null) return "";
  return DIFFICULTY_LABELS[v] ?? String(v);
}

function formatSectors(v: KeySector[] | null | undefined): string {
  if (!v || v.length === 0) return "";
  return v.map((s) => KEY_SECTOR_LABELS[s] ?? s).join(", ");
}

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function EmptyPlaceholder({ label }: { label: string }) {
  return (
    <span className="text-[rgba(34,42,53,0.35)]" aria-label={`Sin registro de ${label}`}>
      — sin registro —
    </span>
  );
}

interface ConditionRowProps {
  label: string;
  value: string | null | undefined;
}

function ConditionRow({ label, value }: ConditionRowProps) {
  const filled = value != null && value !== "";
  return (
    <div>
      <p className="text-[11px] font-medium text-mid-gray">{label}</p>
      {filled ? (
        <p className="text-sm text-charcoal">{value}</p>
      ) : (
        <p className="text-sm">
          <EmptyPlaceholder label={label} />
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CourseDescriptionCardProps {
  /** ID de la válida — requerido para la mutation de actualización. */
  raceEventId: number;
  /** Descripción actual del circuito (`data.description` de `useRaceCourse`). */
  description: Partial<CourseDescription> | null | undefined;
  /** true para el rol parent — solo lectura, sin botón de edición. */
  readOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CourseDescriptionCard({
  raceEventId,
  description,
  readOnly = false,
}: CourseDescriptionCardProps) {
  const [editOpen, setEditOpen] = useState(false);

  const d = description ?? {};
  const filled = countFilledFields(d);

  // Estado derivado — con solo 4 campos posibles, "completo" exige los 4.
  const state: "empty" | "partial" | "complete" =
    filled === 0 ? "empty" : filled === 4 ? "complete" : "partial";

  // Parent + nada registrado: no mostrar ni siquiera el estado vacío.
  if (state === "empty" && readOnly) {
    return null;
  }

  // ── Estado vacío (coach/admin) ──────────────────────────────────────────
  if (state === "empty") {
    return (
      <div
        className="flex items-center justify-between rounded-card bg-surface-raised px-4 py-3 shadow-card ring-1 ring-hairline"
        data-testid="course-description-card-empty"
      >
        <p className="text-sm text-mid-gray">
          Descripción del circuito no registrada
        </p>
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className="min-h-[48px] rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90"
          data-testid="course-description-describe-btn"
        >
          Describir la pista
        </button>
        {editOpen && (
          <Suspense fallback={null}>
            <EditCourseDescriptionDialog
              raceEventId={raceEventId}
              currentDescription={d}
              open={editOpen}
              onOpenChange={setEditOpen}
            />
          </Suspense>
        )}
      </div>
    );
  }

  // ── Estado parcial o completo ────────────────────────────────────────────
  const terrainValue = formatTerrain(d.terrain_type);
  const difficultyValue = formatDifficulty(d.technical_difficulty);
  const sectorsValue = formatSectors(d.key_sectors);
  const notesValue =
    d.course_notes && d.course_notes.trim() !== "" ? d.course_notes : "";

  // Coach/admin siempre ve las 4 filas (con placeholder gris para lo que
  // falta, para invitar a completarlo); parent solo ve lo que sí está lleno.
  const showTerrainRow = !readOnly || terrainValue !== "";
  const showDifficultyRow = !readOnly || difficultyValue !== "";
  const showSectorsRow = !readOnly || sectorsValue !== "";
  const showNotesRow = !readOnly || notesValue !== "";

  const buttonLabel = state === "partial" ? "Completar" : "Editar";
  const buttonClass =
    state === "partial"
      ? "bg-charcoal text-surface hover:opacity-90"
      : "bg-surface-raised text-charcoal ring-1 ring-[rgba(34,42,53,0.12)] hover:bg-light-gray";

  return (
    <div
      className="rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline"
      data-testid={`course-description-card-${state}`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-charcoal">
          Descripción del circuito
        </h3>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className={`min-h-[48px] rounded-lg px-4 py-2 text-sm font-medium transition-colors ${buttonClass}`}
            data-testid="course-description-edit-btn"
          >
            {buttonLabel}
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
        {showTerrainRow && <ConditionRow label="Tipo de superficie" value={terrainValue} />}
        {showDifficultyRow && (
          <ConditionRow label="Dificultad técnica" value={difficultyValue} />
        )}
        {showSectorsRow && (
          <ConditionRow label="Sectores clave" value={sectorsValue} />
        )}
        {showNotesRow && (
          <div className="col-span-2 sm:col-span-3">
            <p className="text-[11px] font-medium text-mid-gray">Notas</p>
            {notesValue !== "" ? (
              <p className="text-sm text-charcoal">{notesValue}</p>
            ) : (
              <p className="text-sm">
                <EmptyPlaceholder label="notas" />
              </p>
            )}
          </div>
        )}
      </div>

      {!readOnly && editOpen && (
        <Suspense fallback={null}>
          <EditCourseDescriptionDialog
            raceEventId={raceEventId}
            currentDescription={d}
            open={editOpen}
            onOpenChange={setEditOpen}
          />
        </Suspense>
      )}
    </div>
  );
}
