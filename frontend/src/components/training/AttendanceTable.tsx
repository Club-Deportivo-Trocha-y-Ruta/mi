import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Control } from "react-hook-form";
import { Controller } from "react-hook-form";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  RefreshCw,
} from "lucide-react";

import type { Attendance, AttendanceStatus } from "@/types/trainingSession.types";
import type { ActivityOut } from "@/types/strava.types";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import { ActivityEvidenceStrip } from "./ActivityEvidenceStrip";
import { RubricSliders } from "./RubricSliders";
import { RPE_FACES, RPE_LABELS, rpeSegmentColor } from "./rubricConstants";
import { ALLOWS_RUBRIC, REQUIRES_REASON, useAttendanceForm } from "./useAttendanceForm";

/**
 * Feature 041 — gobernanza multi-coach (T067, contracts/session-coaches.md
 * §6.1, §10.4). `AttendanceRead` gana `recorded_by_display_name` y
 * `last_edited_by_display_name` en el backend; no se agregaron a `Attendance`
 * en `types/trainingSession.types.ts` porque ese archivo pertenece a otra
 * tarea de esta ola (T066, fuera del alcance de archivos que T067 puede
 * tocar) — se modela aquí como extensión local aditiva del mismo tipo. Coach/
 * admin surface únicamente: el padre nunca ve estos campos (§6.1: el backend
 * los descarta al revalidar hacia `AttendanceReadParent`; `ReadOnlyAttendanceRow`,
 * usado por `ParentSessionDetailPage`, no importa este tipo).
 */
export type AttendanceWithAttribution = Attendance & {
  recorded_by_display_name?: string | null;
  last_edited_by_display_name?: string | null;
};

/**
 * Línea "Registrado por {A} · Editado por {B}" bajo el nombre del atleta.
 * `null` cuando no hay nada que mostrar — filas de antes de esta feature no
 * traen ninguno de los dos campos (data-model.md §6.3: no se hizo backfill),
 * y el requisito es "renderizar nada antes que adivinar" (nunca inventar un
 * nombre). Si `recorded_by_display_name` falta pero el de edición sí vino
 * (caso no documentado por el contrato), se opta por omitir la línea
 * completa en vez de mostrar un "Editado por" huérfano sin quién registró.
 */
function attendanceAttributionLine(a: AttendanceWithAttribution): string | null {
  const recorded = a.recorded_by_display_name ?? null;
  const edited = a.last_edited_by_display_name ?? null;
  if (!recorded) return null;
  if (!edited || edited === recorded) return `Registrado por ${recorded}`;
  return `Registrado por ${recorded} · Editado por ${edited}`;
}

export interface AttendanceFormValues {
  status: AttendanceStatus;
  excuse_reason: string | null;
  rpe_omni: number | null;
  rubric_effort: number | null;
  rubric_attitude: number | null;
  rubric_technique: number | null;
  individual_feedback: string | null;
}

const STATUS_LABELS: Record<AttendanceStatus, string> = {
  presente: "Presente",
  ausente: "Ausente",
  justificado: "Justificado",
  tarde: "Tarde",
  lesionado: "Lesionado",
};

const STATUS_ORDER: AttendanceStatus[] = ["presente", "ausente", "justificado", "tarde", "lesionado"];

// Color por estado activo, ajustado al feedback del coach 2026-09-11
// (revisión de la pantalla real): solo verde y ámbar, ambos parte del
// vocabulario de estados de la constitución (`--color-success`/`-warning`);
// ausente/justificado/lesionado comparten un neutro `charcoal` — no son un
// semáforo de tres colores negativos, son variantes de "no presente".
const STATUS_ITEM_ACTIVE_CLASS: Record<AttendanceStatus, string> = {
  presente: "data-[state=on]:bg-[var(--color-success)] data-[state=on]:text-white",
  tarde: "data-[state=on]:bg-[var(--color-warning)] data-[state=on]:text-charcoal",
  ausente: "data-[state=on]:bg-charcoal data-[state=on]:text-white",
  justificado: "data-[state=on]:bg-charcoal data-[state=on]:text-white",
  lesionado: "data-[state=on]:bg-charcoal data-[state=on]:text-white",
};

const STATUS_KEY_MAP: Record<string, AttendanceStatus> = {
  p: "presente",
  a: "ausente",
  j: "justificado",
  t: "tarde",
  l: "lesionado",
};

const ABSENCE_STATUSES: AttendanceStatus[] = ["ausente", "justificado", "lesionado"];

/**
 * RPE OMNI, Esfuerzo, Actitud y Técnica son OPCIONALES (pedido del coach:
 * una sesión de recuperación con fisioterapia no tiene ni RPE ni técnica) —
 * "hay evaluación" significa que AL MENOS uno de los 4 campos tiene valor o
 * hay comentario, nunca que estén completos. Sirve tanto para los valores ya
 * guardados en el servidor (`AttendanceWithAttribution`) como para los
 * valores en vivo del formulario (`Partial<AttendanceFormValues>`) — mismos
 * nombres de campo en ambos tipos.
 */
interface EvaluationFieldsShape {
  rpe_omni?: number | null;
  rubric_effort?: number | null;
  rubric_attitude?: number | null;
  rubric_technique?: number | null;
  individual_feedback?: string | null;
}

function hasAnyEvaluationValue(a: EvaluationFieldsShape): boolean {
  return (
    a.rpe_omni != null ||
    a.rubric_effort != null ||
    a.rubric_attitude != null ||
    a.rubric_technique != null ||
    !!(a.individual_feedback && a.individual_feedback.trim())
  );
}

/** ¿Ya hay una evaluación (parcial o completa) guardada en el servidor? */
const hasStoredEvaluation = hasAnyEvaluationValue;

function needsReason(a: AttendanceWithAttribution): boolean {
  return REQUIRES_REASON.includes(a.status) && !(a.excuse_reason ?? "").trim();
}

/** Normaliza para búsqueda insensible a acentos/mayúsculas. */
function normalizeForSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

type FilterKey = "todos" | "presentes" | "sin_evaluar" | "falta_razon" | "ausencias";

const FILTER_LABELS: Record<FilterKey, string> = {
  todos: "Todos",
  presentes: "Presentes",
  sin_evaluar: "Sin evaluar",
  falta_razon: "Falta razón",
  ausencias: "Ausencias",
};

function matchesFilter(a: AttendanceWithAttribution, filter: FilterKey): boolean {
  switch (filter) {
    case "todos":
      return true;
    case "presentes":
      return a.status === "presente";
    case "sin_evaluar":
      return ALLOWS_RUBRIC.includes(a.status) && !hasStoredEvaluation(a);
    case "falta_razon":
      return needsReason(a);
    case "ausencias":
      return ABSENCE_STATUSES.includes(a.status);
  }
}

// ─── Control segmentado de Estado ───────────────────────────────────────────

// Continuo (sin huecos, redondeado solo en los extremos vía las clases
// `data-[spacing=0]:first/last` del wrapper de `ToggleGroup`) con la PALABRA
// completa visible — feedback del coach 2026-09-11: las letras P/A/J/T/L
// resultaban crípticas.
const statusItemBaseClass =
  "min-h-12 flex-1 shrink-0 border-r border-[rgba(34,42,53,0.15)] px-2 text-xs font-medium text-charcoal transition-colors last:border-r-0";

function StatusToggleGroup({
  control,
  disabled,
}: {
  control: Control<AttendanceFormValues>;
  disabled?: boolean;
}) {
  return (
    <Controller
      name="status"
      control={control}
      render={({ field }) => (
        <ToggleGroup
          type="single"
          value={field.value}
          onValueChange={(v) => {
            if (v) field.onChange(v as AttendanceStatus);
          }}
          disabled={disabled}
          aria-label="Estado de asistencia"
          className="flex w-full overflow-hidden rounded-lg shadow-ring"
        >
          {STATUS_ORDER.map((key) => (
            <ToggleGroupItem
              key={key}
              value={key}
              aria-label={STATUS_LABELS[key]}
              className={cn(statusItemBaseClass, STATUS_ITEM_ACTIVE_CLASS[key])}
            >
              {STATUS_LABELS[key]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
    />
  );
}

// ─── Resumen compacto de evaluación (chips) ─────────────────────────────────

function EvaluationSummary({
  rubricEnabled,
  formValues,
}: {
  rubricEnabled: boolean;
  formValues: Partial<AttendanceFormValues>;
}) {
  if (!rubricEnabled) {
    return <span className="text-xs text-mid-gray">No aplica</span>;
  }

  // RPE/Esfuerzo/Actitud/Técnica son opcionales — una evaluación parcial
  // (p. ej. solo Actitud + comentario) es válida: se muestra únicamente el
  // chip del campo que sí tiene valor, nunca se inventan los otros tres.
  if (!hasAnyEvaluationValue(formValues)) {
    return (
      <span className="inline-flex items-center rounded-full bg-light-gray px-2 py-0.5 text-xs text-mid-gray">
        Sin evaluar
      </span>
    );
  }

  const { rpe_omni: rpe, rubric_effort: effort, rubric_attitude: attitude, rubric_technique: technique } =
    formValues;
  const comment = formValues.individual_feedback ?? "";

  // Legible en vez de decodificable (feedback del coach 2026-09-11): un chip
  // de color para RPE (misma rampa que `RpeScale`) + una sola línea de texto
  // con las palabras completas de las rúbricas que sí tienen valor — nunca
  // "E 5 A 5 T 5".
  const rubricParts: string[] = [];
  if (effort != null) rubricParts.push(`Esfuerzo ${effort}`);
  if (attitude != null) rubricParts.push(`Actitud ${attitude}`);
  if (technique != null) rubricParts.push(`Técnica ${technique}`);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {rpe != null && (
        <span
          className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium text-white"
          style={{ backgroundColor: rpeSegmentColor(rpe) }}
          title={`RPE OMNI: ${rpe} — ${RPE_LABELS[rpe]}`}
          aria-label={`RPE OMNI: ${rpe} — ${RPE_LABELS[rpe]}`}
        >
          <span aria-hidden="true">{RPE_FACES[rpe]}</span> RPE {rpe}
        </span>
      )}
      {rubricParts.length > 0 && (
        <span className="text-xs text-mid-gray">{rubricParts.join(" · ")}</span>
      )}
      {comment.trim() && (
        <span title="Con comentario del coach">
          <MessageSquare
            size={13}
            className="text-mid-gray"
            aria-label="Con comentario del coach"
          />
        </span>
      )}
    </div>
  );
}

// ─── Botón Evaluar / Cerrar ──────────────────────────────────────────────────

function EvaluateToggleButton({
  expanded,
  hasEvaluation,
  panelId,
  athleteName,
  onToggle,
}: {
  expanded: boolean;
  hasEvaluation: boolean;
  panelId: string;
  athleteName: string;
  onToggle: () => void;
}) {
  // Texto visible corto ("Evaluar"/"Editar"/"Cerrar", pedido del coach
  // 2026-09-11 — distingue "aún no evaluado" de "ya evaluado, quiero verlo o
  // ajustarlo") + `aria-label` con el nombre del atleta: con 15-25 filas en
  // pantalla, un lector de pantalla que navegue por botones oiría el mismo
  // texto repetido de forma ambigua sin el nombre. `aria-label` reemplaza el
  // nombre accesible por completo, así que el ícono y el texto van `aria-hidden`.
  const label = expanded ? "Cerrar" : hasEvaluation ? "Editar" : "Evaluar";
  const fullLabel = expanded
    ? `Cerrar evaluación de ${athleteName}`
    : hasEvaluation
      ? `Editar evaluación de ${athleteName}`
      : `Evaluar a ${athleteName}`;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      aria-controls={panelId}
      aria-label={fullLabel}
      className="inline-flex min-h-12 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70"
    >
      {expanded ? (
        <ChevronUp size={14} aria-hidden="true" />
      ) : (
        <ChevronDown size={14} aria-hidden="true" />
      )}
      <span aria-hidden="true">{label}</span>
    </button>
  );
}

interface AttendanceRowProps {
  attendance: AttendanceWithAttribution;
  sessionId: number;
  disabled?: boolean;
  linkedActivities: ActivityOut[];
  unlinkedActivities: ActivityOut[];
  activitiesLoading: boolean;
  canLink: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
}

function AttendanceRow({
  attendance,
  sessionId,
  disabled,
  linkedActivities,
  unlinkedActivities,
  activitiesLoading,
  canLink,
  expanded,
  onToggleExpand,
}: AttendanceRowProps) {
  const rowRef = useRef<HTMLTableRowElement>(null);
  const reasonInputRef = useRef<HTMLInputElement | null>(null);

  const {
    control,
    register,
    setValue,
    formValues,
    savedIndicator,
    doSave,
    requiresReason,
    allowsRubric,
    needsReasonAlert,
  } = useAttendanceForm(attendance, sessionId, disabled);

  const rubricEnabled = allowsRubric && !disabled;
  const feedbackVal = formValues.individual_feedback ?? "";

  useEffect(() => {
    if (needsReasonAlert) reasonInputRef.current?.focus();
  }, [needsReasonAlert]);

  const reasonField = register("excuse_reason");

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTableRowElement>) => {
      const tag = (e.target as HTMLElement).tagName.toLowerCase();
      // "button" incluye el chevron/"Enlazar" del ActivityEvidenceStrip y el
      // botón Evaluar/Cerrar — esos botones deben recibir Tab/Enter
      // normalmente, no ser interceptados por los atajos P/A/J/T/L de la fila.
      if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") return;
      const mapped = STATUS_KEY_MAP[e.key.toLowerCase()];
      if (mapped) setValue("status", mapped, { shouldDirty: true });
    },
    [setValue],
  );

  const clearEvaluation = useCallback(() => {
    setValue("rpe_omni", null, { shouldDirty: true });
    setValue("rubric_effort", null, { shouldDirty: true });
    setValue("rubric_attitude", null, { shouldDirty: true });
    setValue("rubric_technique", null, { shouldDirty: true });
    setValue("individual_feedback", null, { shouldDirty: true });
  }, [setValue]);

  const athleteName =
    attendance.athlete_name ?? `Atleta #${attendance.athlete_id}`;
  const attributionLine = attendanceAttributionLine(attendance);
  const panelId = `rubric-panel-${attendance.athlete_id}`;

  return (
    <>
      <tr
        ref={rowRef}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        aria-keyshortcuts="p a j t l"
        className="group focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
        style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
        data-testid={`attendance-row-${attendance.athlete_id}`}
      >
        {/* Atleta */}
        <td className="px-3 py-2 align-top text-sm font-medium text-charcoal">
          <div className="flex items-center gap-2">
            {athleteName}
            <span role="status" aria-live="polite" aria-atomic="true">
              {savedIndicator === "saved" && (
                <CheckCircle2
                  size={14}
                  className="animate-fade-in text-green-600"
                  aria-label="Guardado"
                  data-testid="saved-indicator"
                />
              )}
              {savedIndicator === "error" && !needsReasonAlert && (
                <span
                  className="flex items-center gap-1 text-xs text-red-600"
                  title="Error al guardar"
                >
                  <AlertCircle size={14} aria-hidden="true" />
                  Error
                  <button
                    type="button"
                    onClick={() => doSave(formValues as AttendanceFormValues)}
                    className="ml-1 underline hover:opacity-70"
                    data-testid="retry-button"
                  >
                    <RefreshCw size={12} aria-label="Reintentar" />
                  </button>
                </span>
              )}
              {needsReasonAlert && (
                <span
                  className="flex items-center gap-1 text-xs text-amber-600"
                  title="Falta razón"
                  data-testid="needs-reason-alert"
                >
                  <AlertTriangle size={14} aria-hidden="true" />
                  Falta razón
                </span>
              )}
            </span>
          </div>
          {attributionLine && (
            <p
              className="mt-0.5 text-xs text-mid-gray"
              data-testid={`attendance-attribution-${attendance.athlete_id}`}
            >
              {attributionLine}
            </p>
          )}
          <div className="mt-1.5">
            <ActivityEvidenceStrip
              athleteId={attendance.athlete_id}
              linkedActivities={linkedActivities}
              unlinkedActivities={unlinkedActivities}
              loading={activitiesLoading}
              canLink={canLink}
            />
          </div>
        </td>

        {/* Estado — la razón (cuando el estado la requiere) vive debajo del
            control en la misma celda; se eliminó la columna "Razón" propia
            (feedback del coach 2026-09-11: quedaba casi siempre vacía). */}
        <td className="px-3 py-2 align-top">
          <div className="space-y-1.5">
            <StatusToggleGroup control={control} disabled={disabled} />
            {requiresReason && (
              <div className="flex flex-col gap-1">
                <input
                  {...reasonField}
                  ref={(el) => {
                    reasonField.ref(el);
                    reasonInputRef.current = el;
                  }}
                  type="text"
                  disabled={disabled}
                  placeholder="Razón (requerida)"
                  maxLength={300}
                  aria-label="Razón de ausencia"
                  aria-required="true"
                  aria-invalid={needsReasonAlert}
                  aria-describedby={needsReasonAlert ? `reason-help-${attendance.athlete_id}` : undefined}
                  className="w-full min-w-[140px] rounded-lg px-2.5 py-1.5 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
                  style={
                    needsReasonAlert
                      ? { boxShadow: "rgba(217, 119, 6, 0.5) 0px 0px 0px 2px" }
                      : undefined
                  }
                />
                {needsReasonAlert && (
                  <p
                    id={`reason-help-${attendance.athlete_id}`}
                    className="text-[10px] text-amber-700"
                  >
                    Escribe una razón para guardar este estado
                  </p>
                )}
              </div>
            )}
          </div>
        </td>

        {/* Evaluación */}
        <td className="px-3 py-2 align-top">
          <EvaluationSummary rubricEnabled={rubricEnabled} formValues={formValues} />
        </td>

        {/* Acción */}
        <td className="px-3 py-2 align-top">
          {rubricEnabled && (
            <EvaluateToggleButton
              expanded={expanded}
              hasEvaluation={hasAnyEvaluationValue(formValues)}
              panelId={panelId}
              athleteName={athleteName}
              onToggle={onToggleExpand}
            />
          )}
        </td>
      </tr>

      {rubricEnabled && expanded && (
        <tr style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}>
          <td className="px-3 pb-3 pt-0" colSpan={4}>
            <div
              id={panelId}
              role="region"
              aria-label={`Evaluación de ${athleteName}`}
              className="rounded-lg bg-light-gray/60 p-3"
            >
              <RubricSliders
                control={control}
                disabled={!rubricEnabled}
                feedbackLength={feedbackVal?.length ?? 0}
                onClear={clearEvaluation}
              />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function AttendanceCard({
  attendance,
  sessionId,
  disabled,
  linkedActivities,
  unlinkedActivities,
  activitiesLoading,
  canLink,
  expanded,
  onToggleExpand,
}: AttendanceRowProps) {
  const reasonInputRef = useRef<HTMLInputElement | null>(null);
  const {
    control,
    register,
    setValue,
    formValues,
    savedIndicator,
    doSave,
    requiresReason,
    allowsRubric,
    needsReasonAlert,
  } = useAttendanceForm(attendance, sessionId, disabled);

  const rubricEnabled = allowsRubric && !disabled;
  const feedbackVal = formValues.individual_feedback ?? "";

  const clearEvaluation = useCallback(() => {
    setValue("rpe_omni", null, { shouldDirty: true });
    setValue("rubric_effort", null, { shouldDirty: true });
    setValue("rubric_attitude", null, { shouldDirty: true });
    setValue("rubric_technique", null, { shouldDirty: true });
    setValue("individual_feedback", null, { shouldDirty: true });
  }, [setValue]);

  useEffect(() => {
    if (needsReasonAlert) reasonInputRef.current?.focus();
  }, [needsReasonAlert]);

  const reasonField = register("excuse_reason");

  const athleteName = attendance.athlete_name ?? `Atleta #${attendance.athlete_id}`;
  const attributionLine = attendanceAttributionLine(attendance);
  const panelId = `rubric-panel-card-${attendance.athlete_id}`;

  return (
    <div className="rounded-xl bg-white p-4 space-y-3 shadow-ring" data-testid={`attendance-card-${attendance.athlete_id}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-charcoal">{athleteName}</p>
          {attributionLine && (
            <p
              className="mt-0.5 text-xs text-mid-gray"
              data-testid={`attendance-attribution-${attendance.athlete_id}`}
            >
              {attributionLine}
            </p>
          )}
        </div>
        <span role="status" aria-live="polite" aria-atomic="true" className="flex items-center gap-2">
          {savedIndicator === "saved" && (
            <CheckCircle2 size={14} className="text-green-600" aria-label="Guardado" data-testid="saved-indicator" />
          )}
          {savedIndicator === "error" && !needsReasonAlert && (
            <button
              type="button"
              onClick={() => doSave(formValues as AttendanceFormValues)}
              className="text-xs text-red-600 underline"
              data-testid="retry-button"
            >
              Error — reintentar
            </button>
          )}
          {needsReasonAlert && (
            <span
              className="flex items-center gap-1 text-xs text-amber-600"
              data-testid="needs-reason-alert"
            >
              <AlertTriangle size={12} aria-hidden="true" />
              Falta razón
            </span>
          )}
        </span>
      </div>

      <StatusToggleGroup control={control} disabled={disabled} />

      <ActivityEvidenceStrip
        athleteId={attendance.athlete_id}
        linkedActivities={linkedActivities}
        unlinkedActivities={unlinkedActivities}
        loading={activitiesLoading}
        canLink={canLink}
      />

      {requiresReason && (
        <div className="flex flex-col gap-1">
          <input
            {...reasonField}
            ref={(el) => {
              reasonField.ref(el);
              reasonInputRef.current = el;
            }}
            type="text"
            disabled={disabled}
            placeholder="Razón (requerida)"
            maxLength={300}
            aria-label="Razón de ausencia"
            aria-required="true"
            aria-invalid={needsReasonAlert}
            aria-describedby={needsReasonAlert ? `reason-help-card-${attendance.athlete_id}` : undefined}
            className="w-full rounded-lg px-2.5 py-1.5 text-xs text-charcoal placeholder:text-mid-gray outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-40 shadow-ring"
            style={
              needsReasonAlert
                ? { boxShadow: "rgba(217, 119, 6, 0.5) 0px 0px 0px 2px" }
                : undefined
            }
          />
          {needsReasonAlert && (
            <p
              id={`reason-help-card-${attendance.athlete_id}`}
              className="text-[10px] text-amber-700"
            >
              Escribe una razón para guardar este estado
            </p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <EvaluationSummary rubricEnabled={rubricEnabled} formValues={formValues} />
        {rubricEnabled && (
          <EvaluateToggleButton
            expanded={expanded}
            hasEvaluation={hasAnyEvaluationValue(formValues)}
            panelId={panelId}
            athleteName={athleteName}
            onToggle={onToggleExpand}
          />
        )}
      </div>

      {rubricEnabled && expanded && (
        // `role="group"` (no `role="region"`) a propósito: la fila de
        // escritorio (`AttendanceRow`) y esta card se renderizan a la vez en
        // jsdom (responsividad solo CSS, ver comentarios en los tests) — dos
        // landmarks `region` con el mismo nombre accesible disparan
        // "landmark-unique" en axe. En un navegador real solo una de las dos
        // variantes está en el árbol de accesibilidad a la vez (`hidden`),
        // así que aquí basta un contenedor con nombre accesible sin rol de
        // landmark; la variante de escritorio conserva `role="region"`.
        <div
          id={panelId}
          role="group"
          aria-label={`Evaluación de ${athleteName}`}
          className="rounded-lg bg-light-gray/60 p-3"
        >
          <RubricSliders
            control={control}
            disabled={!rubricEnabled}
            feedbackLength={feedbackVal?.length ?? 0}
            onClear={clearEvaluation}
          />
        </div>
      )}
    </div>
  );
}

// ─── Barra superior: resumen + filtro + búsqueda + acciones globales ───────

interface AttendanceSummaryBarProps {
  total: number;
  presentesCount: number;
  tardeCount: number;
  ausenciasCount: number;
  sinEvaluarCount: number;
  sinRazonCount: number;
  filter: FilterKey;
  onFilterChange: (f: FilterKey) => void;
  filterCounts: Record<FilterKey, number>;
  search: string;
  onSearchChange: (v: string) => void;
  showSearch: boolean;
  showBulkButtons: boolean;
  onEvaluateAllVisible: () => void;
  onCollapseAllVisible: () => void;
}

function AttendanceSummaryBar({
  total,
  presentesCount,
  tardeCount,
  ausenciasCount,
  sinEvaluarCount,
  sinRazonCount,
  filter,
  onFilterChange,
  filterCounts,
  search,
  onSearchChange,
  showSearch,
  showBulkButtons,
  onEvaluateAllVisible,
  onCollapseAllVisible,
}: AttendanceSummaryBarProps) {
  return (
    <div
      className="sticky top-0 z-10 flex flex-col gap-2 bg-white pb-2 pt-1"
      style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}
      data-testid="attendance-toolbar"
    >
      <p className="text-xs text-mid-gray" aria-live="polite" data-testid="attendance-summary">
        {total} convocados · {presentesCount} presentes · {tardeCount} tarde · {ausenciasCount} ausencias ·{" "}
        {sinEvaluarCount} sin evaluar · {sinRazonCount} sin razón
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          value={filter}
          onValueChange={(v) => {
            if (v) onFilterChange(v as FilterKey);
          }}
          aria-label="Filtrar asistencia"
          className="flex flex-wrap gap-1.5"
        >
          {(Object.keys(FILTER_LABELS) as FilterKey[]).map((key) => (
            <ToggleGroupItem
              key={key}
              value={key}
              className="min-h-11 rounded-full border border-[rgba(34,42,53,0.12)] px-3 text-xs font-medium text-charcoal data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white"
            >
              {FILTER_LABELS[key]} ({filterCounts[key]})
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        {showBulkButtons && (
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={onEvaluateAllVisible}
              className="min-h-11 rounded-lg px-3 text-xs font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70"
              data-testid="evaluate-all-button"
            >
              Evaluar todos
            </button>
            <button
              type="button"
              onClick={onCollapseAllVisible}
              className="min-h-11 rounded-lg px-3 text-xs font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70"
              data-testid="collapse-all-button"
            >
              Cerrar todos
            </button>
          </div>
        )}
      </div>

      {showSearch && (
        <input
          type="search"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label="Buscar atleta"
          placeholder="Buscar atleta…"
          className="w-full max-w-xs rounded-lg px-2.5 py-2 text-xs text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 shadow-ring"
          data-testid="attendance-search-input"
        />
      )}
    </div>
  );
}

interface AttendanceTableProps {
  sessionId: number;
  attendances: AttendanceWithAttribution[];
  disabled?: boolean;
  linkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
  unlinkedActivitiesByAthleteId?: Map<number, ActivityOut[]>;
  activitiesLoading?: boolean;
  canLink?: boolean;
}

export function AttendanceTable({
  sessionId,
  attendances,
  disabled,
  linkedActivitiesByAthleteId,
  unlinkedActivitiesByAthleteId,
  activitiesLoading = false,
  canLink = false,
}: AttendanceTableProps) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => new Set());
  const [filter, setFilter] = useState<FilterKey>("todos");
  const [search, setSearch] = useState("");

  const toggleExpand = useCallback((athleteId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(athleteId)) next.delete(athleteId);
      else next.add(athleteId);
      return next;
    });
  }, []);

  const total = attendances.length;
  const presentesCount = useMemo(
    () => attendances.filter((a) => a.status === "presente").length,
    [attendances],
  );
  const tardeCount = useMemo(
    () => attendances.filter((a) => a.status === "tarde").length,
    [attendances],
  );
  const ausenciasCount = useMemo(
    () => attendances.filter((a) => ABSENCE_STATUSES.includes(a.status)).length,
    [attendances],
  );
  const sinEvaluarCount = useMemo(
    () => attendances.filter((a) => ALLOWS_RUBRIC.includes(a.status) && !hasStoredEvaluation(a)).length,
    [attendances],
  );
  const sinRazonCount = useMemo(() => attendances.filter(needsReason).length, [attendances]);

  const filterCounts: Record<FilterKey, number> = {
    todos: total,
    presentes: presentesCount,
    sin_evaluar: sinEvaluarCount,
    falta_razon: sinRazonCount,
    ausencias: ausenciasCount,
  };

  const normalizedSearch = normalizeForSearch(search.trim());
  const filtered = useMemo(() => {
    return attendances
      .filter((a) => matchesFilter(a, filter))
      .filter((a) => {
        if (!normalizedSearch) return true;
        const name = a.athlete_name ?? `Atleta #${a.athlete_id}`;
        return normalizeForSearch(name).includes(normalizedSearch);
      });
  }, [attendances, filter, normalizedSearch]);

  const evaluableVisibleIds = useMemo(
    () => (disabled ? [] : filtered.filter((a) => ALLOWS_RUBRIC.includes(a.status)).map((a) => a.athlete_id)),
    [filtered, disabled],
  );

  const expandAllVisible = useCallback(() => {
    setExpandedIds((prev) => new Set([...prev, ...evaluableVisibleIds]));
  }, [evaluableVisibleIds]);

  const collapseAllVisible = useCallback(() => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      evaluableVisibleIds.forEach((id) => next.delete(id));
      return next;
    });
  }, [evaluableVisibleIds]);

  if (attendances.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-mid-gray">
        No hay atletas convocados en esta sesión.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <AttendanceSummaryBar
        total={total}
        presentesCount={presentesCount}
        tardeCount={tardeCount}
        ausenciasCount={ausenciasCount}
        sinEvaluarCount={sinEvaluarCount}
        sinRazonCount={sinRazonCount}
        filter={filter}
        onFilterChange={setFilter}
        filterCounts={filterCounts}
        search={search}
        onSearchChange={setSearch}
        showSearch={attendances.length > 8}
        showBulkButtons={evaluableVisibleIds.length >= 1}
        onEvaluateAllVisible={expandAllVisible}
        onCollapseAllVisible={collapseAllVisible}
      />

      {filtered.length === 0 ? (
        <p className="py-6 text-center text-sm text-mid-gray">
          Ningún atleta coincide con el filtro.
        </p>
      ) : (
        <>
          {/* Mobile: cards */}
          <div className="flex flex-col gap-3 md:hidden">
            {filtered.map((a) => (
              <AttendanceCard
                key={a.athlete_id}
                attendance={a}
                sessionId={sessionId}
                disabled={disabled}
                linkedActivities={linkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
                unlinkedActivities={unlinkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
                activitiesLoading={activitiesLoading}
                canLink={canLink}
                expanded={expandedIds.has(a.athlete_id)}
                onToggleExpand={() => toggleExpand(a.athlete_id)}
              />
            ))}
          </div>

          {/* Desktop: tabla */}
          <div className="hidden overflow-x-auto md:block">
            <table className="min-w-full text-sm">
              <caption className="sr-only">Asistencia de atletas convocados</caption>
              <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
                <tr>
                  <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Atleta
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Estado
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Razón
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Evaluación
                  </th>
                  <th scope="col" className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <AttendanceRow
                    key={a.athlete_id}
                    attendance={a}
                    sessionId={sessionId}
                    disabled={disabled}
                    linkedActivities={linkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
                    unlinkedActivities={unlinkedActivitiesByAthleteId?.get(a.athlete_id) ?? []}
                    activitiesLoading={activitiesLoading}
                    canLink={canLink}
                    expanded={expandedIds.has(a.athlete_id)}
                    onToggleExpand={() => toggleExpand(a.athlete_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="px-1 text-[10px] text-mid-gray">
        Atajos con la fila enfocada: P Presente · A Ausente · J Justificado · T Tarde · L Lesionado
      </p>
    </div>
  );
}
