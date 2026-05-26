/**
 * RaceConditionsCard — tarjeta tri-estado para condiciones de carrera (F4).
 *
 * Estados:
 *  - Vacío (0 campos): card colapsada + botón "Agregar".
 *  - Parcial (1-3 campos): card con faltantes en placeholder gris neutro + botón "Completar".
 *  - Completo (≥4 campos): card normal con datos en grilla + botón secundario "Editar".
 *
 * Diseño:
 *  - Sin iconos warning, sin colores amarillo/rojo. Solo gris neutro o color del tema.
 *  - Solo coach/admin ven los botones de edición.
 *  - Para parent: card readonly o ausente según el estado.
 *
 * El sheet de edición (EditConditionsDialog) se monta lazy para no impactar
 * el chunk del wizard.
 */
import { useState } from "react";
import { lazy, Suspense } from "react";

import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import {
  SURFACE_CONDITION_LABELS,
} from "@/types/raceEvents.types";
import type {
  RaceEventConditions,
  SurfaceCondition,
} from "@/types/raceEvents.types";

const EditConditionsDialog = lazy(() =>
  import("@/components/race/EditConditionsDialog").then((m) => ({
    default: m.EditConditionsDialog,
  })),
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Cuenta cuántos de los 5 campos de condición están rellenos. */
function countFilledFields(c: Partial<RaceEventConditions>): number {
  let n = 0;
  if (c.climate && c.climate.trim() !== "") n++;
  if (c.temperature_c != null && c.temperature_c !== "") n++;
  if (c.surface_condition != null) n++;
  if (c.altitude_msnm != null) n++;
  if (c.weather_notes && c.weather_notes.trim() !== "") n++;
  return n;
}

function formatTemp(v: string | null | undefined): string {
  if (v == null || v === "") return "";
  const n = parseFloat(v);
  return isNaN(n) ? v : `${n} °C`;
}

function formatAlt(v: number | null | undefined): string {
  if (v == null) return "";
  return `${v} msnm`;
}

function formatSurface(v: SurfaceCondition | null | undefined): string {
  if (v == null) return "";
  return SURFACE_CONDITION_LABELS[v] ?? v;
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

export interface RaceConditionsCardProps {
  /** ID del evento — requerido para la mutation de actualización. */
  raceEventId: number;
  /**
   * Condiciones actuales del evento. Puede venir de `parseResult.conditions`
   * (post-wizard) o de los datos del run/evento cacheados.
   */
  conditions: Partial<RaceEventConditions> | null | undefined;
  /** Callback cuando las condiciones se actualizan exitosamente. */
  onUpdated?: (updated: RaceEventConditions) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RaceConditionsCard({
  raceEventId,
  conditions,
  onUpdated: _onUpdated,
}: RaceConditionsCardProps) {
  const role = useAuthStore((s) => s.user?.role);
  const canEdit = role === UserRole.coach || role === UserRole.admin;

  const [editOpen, setEditOpen] = useState(false);

  const c = conditions ?? {};
  const filled = countFilledFields(c);

  // Estado derivado
  const state: "empty" | "partial" | "complete" =
    filled === 0 ? "empty" : filled >= 4 ? "complete" : "partial";

  // ── Estado vacío ─────────────────────────────────────────────────────────
  if (state === "empty") {
    return (
      <div
        className="flex items-center justify-between rounded-xl bg-white px-4 py-3 ring-1 ring-[rgba(34,42,53,0.08)]"
        data-testid="race-conditions-card-empty"
      >
        <p className="text-sm text-mid-gray">
          Condiciones de carrera no registradas
        </p>
        {canEdit && (
          <>
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="min-h-[48px] rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              data-testid="race-conditions-add-btn"
            >
              Agregar
            </button>
            {editOpen && (
              <Suspense fallback={null}>
                <EditConditionsDialog
                  raceEventId={raceEventId}
                  currentConditions={c}
                  open={editOpen}
                  onOpenChange={setEditOpen}
                />
              </Suspense>
            )}
          </>
        )}
      </div>
    );
  }

  // ── Estado parcial o completo ─────────────────────────────────────────────
  const buttonLabel = state === "partial" ? "Completar" : "Editar";
  const buttonClass =
    state === "partial"
      ? "bg-charcoal text-white hover:opacity-90"
      : "bg-white text-charcoal ring-1 ring-[rgba(34,42,53,0.12)] hover:bg-light-gray";

  return (
    <div
      className="rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid={`race-conditions-card-${state}`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-charcoal">
          Condiciones de carrera
        </h3>
        {canEdit && (
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className={`min-h-[48px] rounded-lg px-4 py-2 text-sm font-medium transition-colors ${buttonClass}`}
            data-testid="race-conditions-edit-btn"
          >
            {buttonLabel}
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
        <ConditionRow
          label="Temperatura"
          value={formatTemp(c.temperature_c)}
        />
        <ConditionRow
          label="Terreno"
          value={formatSurface(c.surface_condition)}
        />
        <ConditionRow
          label="Altitud"
          value={formatAlt(c.altitude_msnm)}
        />
        <ConditionRow
          label="Clima"
          value={c.climate ?? null}
        />
        {(c.weather_notes && c.weather_notes.trim() !== "") && (
          <div className="col-span-2 sm:col-span-3">
            <p className="text-[11px] font-medium text-mid-gray">Notas</p>
            <p className="text-sm text-charcoal">{c.weather_notes}</p>
          </div>
        )}
        {(!c.weather_notes || c.weather_notes.trim() === "") && (
          <div className="col-span-2 sm:col-span-3">
            <p className="text-[11px] font-medium text-mid-gray">Notas</p>
            <p className="text-sm">
              <EmptyPlaceholder label="notas" />
            </p>
          </div>
        )}
      </div>

      {editOpen && (
        <Suspense fallback={null}>
          <EditConditionsDialog
            raceEventId={raceEventId}
            currentConditions={c}
            open={editOpen}
            onOpenChange={setEditOpen}
          />
        </Suspense>
      )}
    </div>
  );
}
