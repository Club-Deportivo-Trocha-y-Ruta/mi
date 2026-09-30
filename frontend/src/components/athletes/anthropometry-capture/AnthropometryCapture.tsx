import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Stepper } from "@/components/shared/Stepper";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAnthropometry, useCreateAnthropometry } from "@/hooks/athletes/useAnthropometry";
import {
  getBenchHeightCm,
  getCaptureMode,
  setCaptureMode,
  type CaptureMode,
} from "@/lib/anthropometry/devicePrefs";
import { type MeasureKey } from "@/lib/anthropometry/measureGuides";
import { getMeasureIllustration } from "@/lib/anthropometry/measureIllustrations";
import {
  anthropometryCaptureSchema,
  toAnthropometryPayload,
  todayISO,
  type AnthropometryCaptureValues,
} from "@/schemas/anthropometryCapture.schema";
import type {
  AnthropometricRecord,
  PlausibilityMeasure,
  SameDateConflictDetail,
} from "@/types/anthropometry.types";
import type { Sex } from "@/types/enums";

import { CapturePrecheckStep } from "./CapturePrecheckStep";
import { CaptureReviewStep, type CaptureSaveIntent } from "./CaptureReviewStep";
import { MeasureStep } from "./MeasureStep";
import { QuickCaptureForm } from "./QuickCaptureForm";

// ---------------------------------------------------------------------------
// Tipos públicos
// ---------------------------------------------------------------------------

/** Lo mínimo del deportista que necesita la captura (edad y sexo solo para cálculos). */
export interface CaptureAthlete {
  id: number;
  sex: Sex;
  /** Solo para PHV y elegibilidad de pliegues; nunca se muestra. */
  birth_date: string;
}

export interface CaptureResult {
  recordId: number;
  intent: CaptureSaveIntent;
  /** Registro creado; ausente cuando un reintento confirmó un guardado previo (409 `same_values`). */
  record?: AnthropometricRecord;
  /** `true` cuando el reintento encontró la medición ya guardada. */
  alreadySaved?: boolean;
}

export interface AnthropometryCaptureProps {
  athlete: CaptureAthlete;
  /** Jornada grupal: fecha fija de la sesión (YYYY-MM-DD). */
  lockedDate?: string;
  onDone: (result: CaptureResult) => void;
  /** Ofrecer «Guardar y agregar pliegues». @default true */
  allowSkinfoldsExit?: boolean;
  /**
   * «Abrir la existente» del diálogo de misma fecha. Por defecto navega a la
   * edición (si `canModify`) o al historial del deportista.
   */
  onOpenExisting?: (recordId: number, canModify: boolean) => void;
}

// ---------------------------------------------------------------------------
// Copias y constantes
// ---------------------------------------------------------------------------

export const OFFLINE_SAVE_MESSAGE =
  "Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.";
export const OFFLINE_OPEN_MESSAGE = "Necesitas conexión a internet para registrar mediciones.";
const GENERIC_SAVE_ERROR = "No se pudo guardar la medición. Intenta de nuevo.";

const PRECHECK_STEP = 0;
const REVIEW_STEP = 5;
const MEASURE_STEPS: readonly MeasureKey[] = [
  "weight",
  "standing_height",
  "sitting_height",
  "arm_span",
];
const STEPS = [
  { label: "Preparación" },
  { label: "Peso" },
  { label: "Talla de pie" },
  { label: "Talla sentado" },
  { label: "Envergadura" },
  { label: "Revisar" },
];

/** Campos del formulario que valida cada paso de medida. */
const STEP_FIELDS: Record<MeasureKey, (keyof AnthropometryCaptureValues)[]> = {
  weight: ["weight_kg"],
  standing_height: ["standing_height_cm"],
  sitting_height: ["sitting_height_cm", "bench_height_cm"],
  arm_span: ["arm_span_cm"],
};

/** Id del input de la captura rápida por medida (para «Volver a medir»). */
const QUICK_INPUT_ID: Record<PlausibilityMeasure, string> = {
  weight: "qc-weight",
  standing_height: "qc-standing",
  sitting_height: "qc-sitting",
  arm_span: "qc-arm-span",
};

const TOGGLE_ITEM_CLASSES =
  "min-h-12 rounded-lg border border-border-gray px-4 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-surface";

// ---------------------------------------------------------------------------
// Errores de guardado
// ---------------------------------------------------------------------------

type SaveFailure =
  | { kind: "network" }
  | { kind: "same_date"; existingRecordId: number; sameValues: boolean }
  | { kind: "other" };

function classifySaveError(err: unknown): SaveFailure {
  if (isAxiosError(err)) {
    if (!err.response) return { kind: "network" };
    const data = err.response.data as Partial<SameDateConflictDetail> | undefined;
    if (
      err.response.status === 409 &&
      data?.detail === "anthropometry_same_date_exists" &&
      typeof data.existing_record_id === "number"
    ) {
      return {
        kind: "same_date",
        existingRecordId: data.existing_record_id,
        sameValues: data.same_values === true,
      };
    }
  }
  return { kind: "other" };
}

function useIsOffline(): boolean {
  const [offline, setOffline] = useState(
    () => typeof navigator !== "undefined" && navigator.onLine === false,
  );
  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return offline;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

/**
 * Captura antropométrica de un deportista (feature 048, T037/T048).
 *
 * - Modo «Guiado»: Preparación → Peso → Talla de pie → Talla sentado →
 *   Envergadura → Revisar, con un único formulario RHF compartido.
 * - Modo «Rápido»: `QuickCaptureForm` y el panel «Revisar» en línea.
 * - Guarda con `useCreateAnthropometry` enviando la talla sentado NETA.
 * - Solo en línea: sin borradores locales (clarificación 1). Un fallo de red
 *   deja los valores en pantalla con «Reintentar»; un reintento que recibe
 *   409 `same_values: true` cuenta como guardado (R4).
 *
 * Privacidad: ningún valor de medición se registra en consola ni en
 * almacenamiento local (solo las dos preferencias del dispositivo).
 */
export function AnthropometryCapture({
  athlete,
  lockedDate,
  onDone,
  allowSkinfoldsExit = true,
  onOpenExisting,
}: AnthropometryCaptureProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isOffline = useIsOffline();

  const [mode, setMode] = useState<CaptureMode>(() => getCaptureMode());
  const [step, setStep] = useState(PRECHECK_STEP);
  /** Valores validados que muestra «Revisar» (talla sentado BRUTA). */
  const [reviewValues, setReviewValues] = useState<AnthropometryCaptureValues | null>(null);

  const form = useForm<AnthropometryCaptureValues>({
    resolver: zodResolver(anthropometryCaptureSchema),
    defaultValues: {
      evaluation_date: lockedDate ?? todayISO(),
      weight_kg: undefined,
      standing_height_cm: undefined,
      sitting_height_cm: undefined,
      arm_span_cm: null,
      bench_height_cm: getBenchHeightCm(),
      notes: null,
    },
  });
  const { watch, setValue, trigger, getValues, formState } = form;
  const errors = formState.errors;

  // --- Guardado ------------------------------------------------------------
  const createMutation = useCreateAnthropometry(athlete.id);
  const [pendingIntent, setPendingIntent] = useState<CaptureSaveIntent | null>(null);
  const [lastIntent, setLastIntent] = useState<CaptureSaveIntent>("finish");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ existingRecordId: number } | null>(null);
  /** El intento anterior terminó sin saber si el servidor guardó (red / 5xx). */
  const unknownOutcomeRef = useRef(false);
  /** Evita dos envíos simultáneos (doble toque). */
  const inFlightRef = useRef(false);

  // Solo se consulta el historial cuando hay un conflicto que resolver.
  const historyQuery = useAnthropometry(conflict ? athlete.id : 0);
  const existingRecord = conflict
    ? (historyQuery.data?.find((r) => r.id === conflict.existingRecordId) ?? null)
    : null;

  const save = async (intent: CaptureSaveIntent) => {
    if (!reviewValues || inFlightRef.current) return;
    inFlightRef.current = true;
    const isRetry = unknownOutcomeRef.current;
    setLastIntent(intent);
    setPendingIntent(intent);
    setSaveError(null);
    try {
      const record = await createMutation.mutateAsync(toAnthropometryPayload(reviewValues));
      unknownOutcomeRef.current = false;
      onDone({ recordId: record.id, intent, record });
    } catch (err) {
      const failure = classifySaveError(err);
      if (failure.kind === "same_date") {
        unknownOutcomeRef.current = false;
        if (failure.sameValues && isRetry) {
          // La respuesta del primer intento se perdió pero el registro sí quedó.
          for (const queryKey of [
            ["anthropometry", athlete.id],
            ["athlete", athlete.id],
            ["growth-summary", athlete.id],
            ["ai", "phv", athlete.id],
          ]) {
            void queryClient.invalidateQueries({ queryKey });
          }
          onDone({ recordId: failure.existingRecordId, intent, alreadySaved: true });
          return;
        }
        setConflict({ existingRecordId: failure.existingRecordId });
      } else {
        unknownOutcomeRef.current = true;
        setSaveError(failure.kind === "network" ? OFFLINE_SAVE_MESSAGE : GENERIC_SAVE_ERROR);
      }
    } finally {
      inFlightRef.current = false;
      setPendingIntent(null);
    }
  };

  // --- Foco al cambiar de paso (contrato de `Stepper`) ----------------------
  const stepContainerRef = useRef<HTMLDivElement>(null);
  const isFirstRenderRef = useRef(true);
  useEffect(() => {
    if (isFirstRenderRef.current) {
      isFirstRenderRef.current = false;
      return;
    }
    if (mode !== "guided") return;
    stepContainerRef.current?.querySelector<HTMLHeadingElement>("h2")?.focus();
  }, [step, mode]);

  // --- Navegación guiada ---------------------------------------------------
  const goToReview = async () => {
    const valid = await trigger();
    if (!valid) {
      const fieldErrors = form.formState.errors;
      const firstInvalid = MEASURE_STEPS.findIndex((key) =>
        STEP_FIELDS[key].some((field) => fieldErrors[field]),
      );
      setStep(firstInvalid >= 0 ? firstInvalid + 1 : PRECHECK_STEP);
      return;
    }
    setReviewValues(getValues());
    setSaveError(null);
    setStep(REVIEW_STEP);
  };

  const nextFromMeasure = async (key: MeasureKey) => {
    const ok = await trigger(STEP_FIELDS[key]);
    if (!ok) return;
    const index = MEASURE_STEPS.indexOf(key);
    if (index === MEASURE_STEPS.length - 1) {
      await goToReview();
    } else {
      setStep(index + 2);
    }
  };

  const rootRef = useRef<HTMLDivElement>(null);
  /** Enfoca el campo de fecha tras cerrarse el diálogo (Radix devuelve el foco al cerrar). */
  const focusDateInput = () => {
    window.setTimeout(() => {
      rootRef.current?.querySelector<HTMLInputElement>('input[type="date"]:not(:disabled)')?.focus();
    }, 150);
  };

  const focusQuickInput = (id: string) => {
    // Espera a que el panel «Revisar» se cierre antes de enfocar.
    window.setTimeout(() => document.getElementById(id)?.focus(), 0);
  };

  const handleRemeasure = (measure: PlausibilityMeasure) => {
    setSaveError(null);
    if (mode === "guided") {
      setStep(MEASURE_STEPS.indexOf(measure) + 1);
    } else {
      setReviewValues(null);
      focusQuickInput(QUICK_INPUT_ID[measure]);
    }
  };

  const handleModeChange = (value: string) => {
    if (value !== "guided" && value !== "quick") return;
    if (value === mode) return;
    setCaptureMode(value);
    setMode(value);
    setSaveError(null);
    if (value === "quick") {
      // Ambos modos comparten el mismo formulario: los valores se conservan.
      setReviewValues(null);
    } else {
      setReviewValues(null);
      setStep(PRECHECK_STEP);
    }
  };

  // --- Diálogo de misma fecha ---------------------------------------------
  const closeConflict = () => setConflict(null);
  const openExisting = () => {
    if (!conflict) return;
    const canModify = existingRecord?.can_modify === true;
    const recordId = conflict.existingRecordId;
    setConflict(null);
    if (onOpenExisting) {
      onOpenExisting(recordId, canModify);
      return;
    }
    navigate(
      canModify
        ? `/athletes/${athlete.id}/anthropometry/${recordId}/edit`
        : `/athletes/${athlete.id}?tab=anthropometry`,
    );
  };
  const changeDate = () => {
    setConflict(null);
    setReviewValues(null);
    if (mode === "guided") {
      setStep(PRECHECK_STEP);
    }
    focusDateInput();
  };

  // --- Render ----------------------------------------------------------------
  const isSaving = createMutation.isPending;
  const evaluationDate = watch("evaluation_date");
  const benchValue = watch("bench_height_cm");

  const review = reviewValues && (
    <CaptureReviewStep
      mode="create"
      athleteId={athlete.id}
      athleteSex={athlete.sex}
      athleteBirthDate={athlete.birth_date}
      values={reviewValues}
      onRemeasure={handleRemeasure}
      onSave={(intent) => void save(intent)}
      isSaving={isSaving}
      pendingIntent={pendingIntent}
      allowSkinfoldsExit={allowSkinfoldsExit}
      saveError={saveError}
      onRetry={saveError ? () => void save(lastIntent) : undefined}
    />
  );

  const renderGuidedStep = () => {
    if (step === PRECHECK_STEP) {
      return (
        <CapturePrecheckStep
          date={evaluationDate}
          onDateChange={(date) => setValue("evaluation_date", date, { shouldValidate: true })}
          dateLocked={!!lockedDate}
          onStart={() => setStep(1)}
          isOffline={isOffline}
        />
      );
    }
    if (step === REVIEW_STEP) {
      return (
        <div className="flex flex-col gap-5">
          {review}
          <Button
            type="button"
            variant="secondary"
            size="lg"
            className="sm:self-start"
            disabled={isSaving}
            onClick={() => setStep(REVIEW_STEP - 1)}
          >
            Anterior
          </Button>
        </div>
      );
    }
    const key = MEASURE_STEPS[step - 1];
    const field = STEP_FIELDS[key][0];
    const isArmSpan = key === "arm_span";
    return (
      <MeasureStep
        key={key}
        measureKey={key}
        value={watch(field) as number | null | undefined}
        onChange={(v) =>
          setValue(field, (isArmSpan ? (v === undefined ? null : v) : v) as never, {
            shouldValidate: formState.isSubmitted || !!errors[field],
          })
        }
        error={errors[field]?.message}
        illustrationSrc={getMeasureIllustration(key)}
        onPrev={() => setStep(step - 1)}
        onNext={() => void nextFromMeasure(key)}
        onSkip={
          isArmSpan
            ? () => {
                setValue("arm_span_cm", null);
                form.clearErrors("arm_span_cm");
                void goToReview();
              }
            : undefined
        }
        {...(key === "sitting_height"
          ? {
              benchValue,
              onBenchChange: (v: number | undefined) =>
                setValue("bench_height_cm", v ?? null, {
                  shouldValidate: !!errors.bench_height_cm,
                }),
              benchError: errors.bench_height_cm?.message,
              persistBench: true,
            }
          : {})}
      />
    );
  };

  return (
    <div ref={rootRef} className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span id="capture-mode-label" className="text-sm font-medium text-charcoal">
          Modo de captura
        </span>
        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={handleModeChange}
          aria-labelledby="capture-mode-label"
          className="flex gap-1.5"
          disabled={isSaving}
        >
          <ToggleGroupItem value="guided" className={TOGGLE_ITEM_CLASSES}>
            Guiado
          </ToggleGroupItem>
          <ToggleGroupItem value="quick" className={TOGGLE_ITEM_CLASSES}>
            Rápido
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {mode === "guided" ? (
        <>
          <Stepper
            steps={STEPS}
            active={step}
            onStepClick={(index) => {
              if (!isSaving) setStep(index);
            }}
            ariaLabel="Pasos de la medición"
          />
          <div ref={stepContainerRef}>{renderGuidedStep()}</div>
        </>
      ) : (
        <div className="flex flex-col gap-6">
          {isOffline && (
            <p role="alert" className="text-sm text-danger">
              {OFFLINE_OPEN_MESSAGE}
            </p>
          )}
          {/* Cualquier cambio en la cuadrícula invalida el panel «Revisar». */}
          <div
            onChange={() => {
              if (reviewValues && !isSaving) setReviewValues(null);
            }}
          >
            <QuickCaptureForm
              form={form}
              dateLocked={!!lockedDate}
              isPending={isSaving || isOffline}
              onReview={(values) => {
                setSaveError(null);
                setReviewValues(values);
              }}
            />
          </div>
          {review}
        </div>
      )}

      <ConfirmDialog
        open={conflict !== null}
        title="Ya existe una medición de esta fecha"
        description={
          lockedDate
            ? "Este deportista ya tiene una medición registrada en la fecha de la jornada. Ábrela para revisarla o corregirla."
            : "Este deportista ya tiene una medición registrada en esa fecha. Ábrela para revisarla o corregirla, o elige otra fecha."
        }
        confirmLabel="Abrir la existente"
        cancelLabel={lockedDate ? "Cerrar" : "Cambiar la fecha"}
        isPending={conflict !== null && historyQuery.isLoading}
        onConfirm={openExisting}
        onCancel={lockedDate ? closeConflict : changeDate}
      />
    </div>
  );
}
