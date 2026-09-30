import { useEffect, useMemo, useRef } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useBodyComposition } from "@/hooks/athletes/useBodyComposition";
import { usePlausibilityCheck } from "@/hooks/athletes/useAnthropometry";
import {
  ageFromBirthDate,
  isIntervalBlocked,
  SKINFOLD_MIN_AGE_YEARS,
} from "@/lib/bodyComposition/eligibility";
import { computeAgeDecimal } from "@/lib/category";
import { formatDate } from "@/lib/datetime";
import { calculatePHV, type PHVResult } from "@/lib/phv";
import {
  netSittingHeight,
  toAnthropometryPayload,
  type AnthropometryCaptureValues,
} from "@/schemas/anthropometryCapture.schema";
import type { PlausibilityMeasure, PlausibilityWarning } from "@/types/anthropometry.types";
import type { Sex } from "@/types/enums";

import { formatDecimal } from "./DecimalInput";
import { PhvPlainSummary } from "./PhvPlainSummary";
import { PlausibilityWarnings } from "./PlausibilityWarnings";

/** Qué salida de guardado eligió el coach. `edit` solo ofrece `finish`. */
export type CaptureSaveIntent = "finish" | "skinfolds";

export interface CaptureReviewStepProps {
  mode: "create" | "edit";
  athleteId: number;
  athleteSex: Sex;
  /** Solo para calcular edad (PHV y elegibilidad de pliegues); nunca se muestra. */
  athleteBirthDate: string;
  /** Valores del formulario: `sitting_height_cm` es la lectura BRUTA. */
  values: AnthropometryCaptureValues;
  /** En edición: excluye el propio registro de «anterior» en la plausibilidad. */
  recordId?: number;
  /** «Volver a medir»: el orquestador salta al paso de esa medida. */
  onRemeasure: (measure: PlausibilityMeasure) => void;
  /** «Está bien así» (opcional, p. ej. para telemetría sin datos). */
  onAcknowledgeWarning?: (warning: PlausibilityWarning) => void;
  /** El orquestador es dueño de la mutación; aquí solo se elige la salida. */
  onSave: (intent: CaptureSaveIntent) => void;
  isSaving?: boolean;
  /** Salida en curso, para mostrar «Guardando…» en el botón correcto. */
  pendingIntent?: CaptureSaveIntent | null;
  /**
   * Ofrecer «Guardar y agregar pliegues» (modo `create`). Default `true`;
   * el orquestador lo apaga cuando no hay a dónde navegar.
   */
  allowSkinfoldsExit?: boolean;
  /** Mensaje de error del guardado (p. ej. sin conexión); los valores quedan en pantalla. */
  saveError?: string | null;
  /** «Reintentar» del banner de error. Si se omite, no se muestra el botón. */
  onRetry?: () => void;
}

interface ValueRow {
  key: string;
  label: string;
  value: string;
  detail?: string;
}

function cm(value: number): string {
  return `${formatDecimal(value)} cm`;
}

function buildRows(values: AnthropometryCaptureValues): ValueRow[] {
  const bench = values.bench_height_cm ?? 0;
  const net = netSittingHeight(values.sitting_height_cm, bench);
  return [
    {
      key: "evaluation_date",
      label: "Fecha de evaluación",
      value: formatDate(`${values.evaluation_date}T12:00:00`),
    },
    { key: "weight", label: "Peso", value: `${formatDecimal(values.weight_kg)} kg` },
    { key: "standing_height", label: "Talla de pie", value: cm(values.standing_height_cm) },
    {
      key: "sitting_height",
      label: "Talla sentado (neta)",
      value: cm(net),
      detail:
        bench > 0
          ? `Lectura ${cm(values.sitting_height_cm)} − banco ${cm(bench)}`
          : undefined,
    },
    {
      key: "arm_span",
      label: "Envergadura",
      value: values.arm_span_cm != null ? cm(values.arm_span_cm) : "No registrada",
    },
  ];
}

/**
 * Paso «Revisar» de la captura antropométrica (feature 048, T036).
 *
 * Presentacional/controlado: muestra los valores (con la talla sentado neta),
 * corre el chequeo de plausibilidad (dry-run, no escribe), el resumen de
 * maduración y las salidas de guardado. La mutación de guardado vive en el
 * orquestador (`AnthropometryCapture`), que recibe `onSave(intent)`.
 */
export function CaptureReviewStep({
  mode,
  athleteId,
  athleteSex,
  athleteBirthDate,
  values,
  recordId,
  onRemeasure,
  onAcknowledgeWarning,
  onSave,
  isSaving = false,
  pendingIntent = null,
  allowSkinfoldsExit = true,
  saveError = null,
  onRetry,
}: CaptureReviewStepProps) {
  const isEdit = mode === "edit";
  const payload = useMemo(() => toAnthropometryPayload(values), [values]);

  // --- Plausibilidad (dry-run) ------------------------------------------
  const plausibility = usePlausibilityCheck(athleteId);
  const { mutate: checkPlausibility } = plausibility;
  const requestKey = JSON.stringify([
    payload.evaluation_date,
    payload.weight_kg,
    payload.standing_height_cm,
    payload.sitting_height_cm,
    payload.arm_span_cm,
    isEdit ? (recordId ?? null) : null,
  ]);
  // Re-chequea solo si cambian los valores. La limpieza del efecto suelta la
  // guarda: en StrictMode (dev) el desmontaje simulado desuscribe el
  // observador de `useMutation` de la mutación en curso, y si el segundo
  // montaje no vuelve a llamar a `mutate` el estado queda en «Revisando las
  // medidas…» para siempre. Un dry-run duplicado en dev es inocuo (no escribe).
  const lastKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (lastKeyRef.current === requestKey) return;
    lastKeyRef.current = requestKey;
    checkPlausibility({
      evaluation_date: payload.evaluation_date,
      weight_kg: payload.weight_kg,
      standing_height_cm: payload.standing_height_cm,
      sitting_height_cm: payload.sitting_height_cm,
      arm_span_cm: payload.arm_span_cm,
      ...(isEdit && recordId != null ? { record_id: recordId } : {}),
    });
    return () => {
      lastKeyRef.current = null;
    };
  }, [requestKey, checkPlausibility, payload, isEdit, recordId]);
  const warnings = plausibility.data?.warnings ?? [];

  // --- PHV en lenguaje llano ---------------------------------------------
  const phv = useMemo<PHVResult | null>(() => {
    const evalDate = new Date(`${payload.evaluation_date}T00:00:00`);
    const birthDate = new Date(`${athleteBirthDate.slice(0, 10)}T00:00:00`);
    if (Number.isNaN(evalDate.getTime()) || Number.isNaN(birthDate.getTime())) return null;
    return calculatePHV({
      sex: athleteSex,
      ageDecimal: computeAgeDecimal(birthDate, evalDate),
      weightKg: payload.weight_kg,
      standingHeightCm: payload.standing_height_cm,
      sittingHeightCm: payload.sitting_height_cm,
    });
  }, [payload, athleteSex, athleteBirthDate]);

  // --- Salida «Guardar y agregar pliegues»
  const skinfoldsWanted = !isEdit && allowSkinfoldsExit;
  const bodyCompositionQuery = useBodyComposition(athleteId, skinfoldsWanted);
  const evaluationDate = payload.evaluation_date;
  const ageAtDate = evaluationDate ? ageFromBirthDate(athleteBirthDate, evaluationDate) : null;
  const skinfoldsAgeOk = ageAtDate !== null && ageAtDate >= SKINFOLD_MIN_AGE_YEARS;
  const nextDueDate = bodyCompositionQuery.data?.next_due_date ?? null;
  const skinfoldsIntervalBlocked =
    !!evaluationDate && isIntervalBlocked(evaluationDate, nextDueDate);
  const showSkinfoldsExit =
    skinfoldsWanted &&
    skinfoldsAgeOk &&
    !bodyCompositionQuery.isLoading &&
    !skinfoldsIntervalBlocked;
  const showIntervalNote = skinfoldsWanted && skinfoldsAgeOk && skinfoldsIntervalBlocked;

  const rows = buildRows(values);
  const savingLabel = "Guardando…";

  return (
    <section aria-labelledby="capture-review-heading" className="flex flex-col gap-5">
      <h2
        id="capture-review-heading"
        className="font-display text-lg text-charcoal"
        tabIndex={-1}
      >
        Revisar
      </h2>

      {/* Valores: lista de definición en teléfono, tabla desde `sm`. */}
      <dl
        className="grid grid-cols-1 gap-3 rounded-card bg-surface-raised p-4 ring-1 ring-hairline sm:hidden"
        data-testid="capture-review-values-list"
      >
        {rows.map((row) => (
          <div key={row.key} className="flex flex-col">
            <dt className="text-xs text-mid-gray">{row.label}</dt>
            <dd className="text-base font-medium text-charcoal">{row.value}</dd>
            {row.detail && <dd className="text-xs text-mid-gray">{row.detail}</dd>}
          </div>
        ))}
      </dl>
      <table
        className="hidden w-full text-sm sm:table"
        data-testid="capture-review-values-table"
      >
        <caption className="sr-only">Valores de la medición</caption>
        <thead>
          <tr className="text-left">
            <th scope="col" className="px-3 py-2 text-xs font-medium uppercase tracking-wide text-mid-gray">
              Medida
            </th>
            <th scope="col" className="px-3 py-2 text-xs font-medium uppercase tracking-wide text-mid-gray">
              Valor
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-hairline">
              <th scope="row" className="px-3 py-2.5 text-left font-normal text-mid-gray">
                {row.label}
              </th>
              <td className="px-3 py-2.5 font-medium text-charcoal">
                {row.value}
                {row.detail && (
                  <span className="block text-xs font-normal text-mid-gray">{row.detail}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {plausibility.isPending && (
        <p className="text-sm text-mid-gray" role="status">
          Revisando las medidas…
        </p>
      )}
      {plausibility.isError && (
        <p className="text-sm text-mid-gray" data-testid="plausibility-check-error">
          No se pudieron revisar las medidas contra la medición anterior. Puedes guardar de
          todas formas.
        </p>
      )}
      {warnings.length > 0 && (
        <PlausibilityWarnings
          warnings={warnings}
          onRemeasure={onRemeasure}
          onAcknowledge={onAcknowledgeWarning}
        />
      )}

      {phv && <PhvPlainSummary phv={phv} />}

      {saveError && (
        <Alert variant="destructive" role="alert" className="flex flex-col gap-3">
          <p>{saveError}</p>
          {onRetry && (
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="self-start"
              onClick={onRetry}
              disabled={isSaving}
            >
              Reintentar
            </Button>
          )}
        </Alert>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        {isEdit ? (
          <Button
            type="button"
            size="lg"
            disabled={isSaving}
            onClick={() => onSave("finish")}
          >
            {isSaving ? savingLabel : "Guardar cambios"}
          </Button>
        ) : (
          <>
            <Button
              type="button"
              size="lg"
              disabled={isSaving}
              onClick={() => onSave("finish")}
            >
              {isSaving && pendingIntent !== "skinfolds" ? savingLabel : "Guardar y terminar"}
            </Button>
            {showSkinfoldsExit && (
              <Button
                type="button"
                variant="secondary"
                size="lg"
                disabled={isSaving}
                onClick={() => onSave("skinfolds")}
              >
                {isSaving && pendingIntent === "skinfolds"
                  ? savingLabel
                  : "Guardar y agregar pliegues"}
              </Button>
            )}
          </>
        )}
      </div>
      {showIntervalNote && nextDueDate && (
        <p className="text-xs text-mid-gray" data-testid="skinfolds-interval-note">
          Pliegues cutáneos: la próxima toma puede hacerse desde el{" "}
          {formatDate(`${nextDueDate.slice(0, 10)}T12:00:00`)}.
        </p>
      )}
    </section>
  );
}
