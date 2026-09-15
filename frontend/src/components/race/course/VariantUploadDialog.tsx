/**
 * VariantUploadDialog — Sheet para subir/reemplazar una variante de circuito
 * (GPX) de una válida (feature 043).
 *
 * Dos modos, según se pase `variantId`:
 *  - Crear (sin `variantId`): pide `label` (prellenado con `defaultLabel`) +
 *    archivo GPX → `POST /course/variants`.
 *  - Reemplazar (`variantId` presente): solo archivo GPX, sin `label` (el
 *    backend lo ignora en este endpoint) → `PUT /course/variants/{id}/file`.
 *
 * Flujo de confirmación de detección (`ui-course.md` §2): tras un upload
 * exitoso se muestra la vuelta detectada y, salvo que sea de un solo tramo
 * (`detection.method === "single"`) o ya se haya forzado `recorded_laps` en
 * este envío, se pregunta si es correcto con dos botones. "No, indicar
 * vueltas" revela un campo numérico y reenvía el MISMO archivo por
 * `PUT .../file` con `recorded_laps` — por eso el `File` se guarda también en
 * estado de componente (`pendingFile`), no solo en RHF: tras esa etapa el
 * input de archivo ya no está montado y no queremos depender de que RHF
 * conserve el valor de un campo no registrado.
 *
 * Privacidad: el GPX es la grabación personal del coach (una vuelta, solo
 * posición + elevación) — no se sube ni se muestra ningún dato de menores en
 * este flujo.
 */
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2 } from "lucide-react";
import { z } from "zod";

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  useReplaceCourseVariantFile,
  useUploadCourseVariant,
} from "@/hooks/race/useRaceCourse";
import { getCourseErrorMessage } from "@/lib/courseErrors";
import { cn } from "@/lib/utils";
import { variantUploadSchema } from "@/schemas/raceCourse";
import type { VariantUploadFormValues } from "@/schemas/raceCourse";
import type { CourseRead, LapDetection } from "@/types/raceCourse.types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface VariantUploadDialogProps {
  raceEventId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Modo crear: nombre sugerido para la primera/segunda variante
   * ("Circuito completo" / "Recorrido reducido", decidido por el caller).
   * Modo reemplazar: se usa como valor interno de `label` (campo oculto —
   * el backend ignora `label` en `PUT .../file`), así que el caller debe
   * pasar el label actual de la variante para que la validación no falle.
   */
  defaultLabel?: string;
  /**
   * Presente → modo "reemplazar archivo" de una variante existente en vez de
   * crear una nueva. Oculta el campo `label`.
   */
  variantId?: number;
}

// ---------------------------------------------------------------------------
// Copy — verbatim de `ui-course.md` §2
// ---------------------------------------------------------------------------

interface DetectionInfo {
  detection: LapDetection;
  lap_distance_km: number;
  elevation_gain_m: number | null;
}

function closedLoopQuestion(info: DetectionInfo): string {
  const elevation = info.elevation_gain_m ?? "sin dato";
  return `Detectamos ${info.detection.laps_detected} vueltas de ${info.lap_distance_km} km (${elevation} m de desnivel). ¿Es correcto?`;
}

function manualQuestion(info: DetectionInfo): string {
  return `No detectamos una vuelta cerrada; se tomó toda la grabación como una vuelta (${info.lap_distance_km} km). Si grabaste varias vueltas, indícalo.`;
}

function successMessage(info: DetectionInfo): string {
  return `Variante guardada: ${info.lap_distance_km} km.`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type Stage = "form" | "question" | "laps-input" | "success";

export function VariantUploadDialog({
  raceEventId,
  open,
  onOpenChange,
  defaultLabel,
  variantId,
}: VariantUploadDialogProps) {
  const isReplaceMode = variantId != null;

  const uploadMutation = useUploadCourseVariant();
  const replaceMutation = useReplaceCourseVariantFile();

  const [stage, setStage] = useState<Stage>("form");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  // Id de la variante recién creada/reemplazada — objetivo del reenvío por
  // `PUT .../file` cuando el coach corrige la detección ("No, indicar vueltas").
  const [targetVariantId, setTargetVariantId] = useState<number | null>(
    variantId ?? null,
  );
  const [detectionInfo, setDetectionInfo] = useState<DetectionInfo | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors },
  } = useForm<
    z.input<typeof variantUploadSchema>,
    unknown,
    VariantUploadFormValues
  >({
    resolver: zodResolver(variantUploadSchema),
    defaultValues: {
      label: defaultLabel ?? "",
      recorded_laps: undefined,
    },
  });

  const watchedRecordedLaps = watch("recorded_laps");

  // Re-sincroniza todo el estado local al abrir el sheet (mismo patrón que
  // `EditConditionsDialog`).
  useEffect(() => {
    if (!open) return;
    reset({ label: defaultLabel ?? "", recorded_laps: undefined });
    setStage("form");
    setPendingFile(null);
    setTargetVariantId(variantId ?? null);
    setDetectionInfo(null);
    setErrorMessage(null);
    uploadMutation.reset();
    replaceMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultLabel, variantId]);

  const isPending = uploadMutation.isPending || replaceMutation.isPending;

  function handleUploadSuccess(
    course: CourseRead,
    opts: { knownVariantId?: number; label?: string; recordedLapsSet: boolean },
  ) {
    const variant =
      opts.knownVariantId != null
        ? course.variants.find((v) => v.id === opts.knownVariantId)
        : opts.label != null
          ? course.variants.find((v) => v.label === opts.label)
          : course.variants[course.variants.length - 1];

    if (!variant) {
      // Defensivo — el backend siempre devuelve la variante recién tocada.
      setStage("success");
      setDetectionInfo(null);
      return;
    }

    setTargetVariantId(variant.id);
    const info: DetectionInfo = {
      detection: variant.detection,
      lap_distance_km: variant.lap_distance_km,
      elevation_gain_m: variant.elevation_gain_m,
    };
    setDetectionInfo(info);

    // Si ya se envió `recorded_laps` en este submit, el método siempre es
    // "manual" (el backend lo fuerza) y no tiene sentido volver a preguntar.
    const shouldAsk =
      !opts.recordedLapsSet &&
      (variant.detection.method === "closed_loop" ||
        variant.detection.method === "manual");

    setStage(shouldAsk ? "question" : "success");
  }

  const onSubmit = handleSubmit((values) => {
    setErrorMessage(null);

    if (stage === "laps-input") {
      // Reenvío tras "No, indicar vueltas": el archivo es SIEMPRE el que ya
      // se subió antes (guardado explícitamente en estado), nunca el del
      // formulario (que en esta etapa ya no está montado).
      if (!pendingFile || targetVariantId == null) return;
      replaceMutation.mutate(
        {
          raceEventId,
          variantId: targetVariantId,
          payload: { file: pendingFile, recorded_laps: values.recorded_laps },
        },
        {
          onSuccess: (course) =>
            handleUploadSuccess(course, {
              knownVariantId: targetVariantId,
              recordedLapsSet: true,
            }),
          onError: (err) => setErrorMessage(getCourseErrorMessage(err)),
        },
      );
      return;
    }

    // Etapa inicial ("form"): crear variante o reemplazar archivo directo.
    setPendingFile(values.file);
    if (isReplaceMode) {
      replaceMutation.mutate(
        {
          raceEventId,
          variantId: variantId!,
          payload: { file: values.file, recorded_laps: values.recorded_laps },
        },
        {
          onSuccess: (course) =>
            handleUploadSuccess(course, {
              knownVariantId: variantId,
              recordedLapsSet: values.recorded_laps != null,
            }),
          onError: (err) => setErrorMessage(getCourseErrorMessage(err)),
        },
      );
    } else {
      uploadMutation.mutate(
        {
          raceEventId,
          payload: {
            file: values.file,
            label: values.label,
            recorded_laps: values.recorded_laps,
          },
        },
        {
          onSuccess: (course) =>
            handleUploadSuccess(course, {
              label: values.label,
              recordedLapsSet: values.recorded_laps != null,
            }),
          onError: (err) => setErrorMessage(getCourseErrorMessage(err)),
        },
      );
    }
  });

  const title = isReplaceMode ? "Reemplazar grabación" : "Agregar variante";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="max-w-md">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {isReplaceMode
              ? "Sube el archivo GPX que reemplaza la grabación de esta variante."
              : "Sube una grabación GPX de una vuelta al circuito (solo posición y elevación)."}
          </SheetDescription>
        </SheetHeader>

        <SheetBody>
          <form
            id="variant-upload-form"
            onSubmit={onSubmit}
            className="space-y-5"
            noValidate
          >
            {(stage === "form" || stage === "laps-input") && (
              <>
                {stage === "form" && (
                  <>
                    {!isReplaceMode && (
                      <div className="space-y-1">
                        <label
                          htmlFor="variant-upload-label"
                          className="block text-xs font-medium text-mid-gray"
                        >
                          Nombre de la variante
                        </label>
                        <input
                          id="variant-upload-label"
                          type="text"
                          maxLength={60}
                          {...register("label")}
                          className={cn(
                            "min-h-12 w-full rounded-lg bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                            "shadow-ring",
                          )}
                          aria-invalid={errors.label ? true : undefined}
                          data-testid="variant-upload-label"
                        />
                        {errors.label && (
                          <p className="text-xs text-red-600" role="alert">
                            {errors.label.message}
                          </p>
                        )}
                      </div>
                    )}

                    <div className="space-y-1">
                      <label
                        htmlFor="variant-upload-file"
                        className="block text-xs font-medium text-mid-gray"
                      >
                        Archivo GPX
                      </label>
                      <Controller
                        control={control}
                        name="file"
                        render={({ field: { onChange, onBlur, name, ref } }) => (
                          <input
                            id="variant-upload-file"
                            ref={ref}
                            name={name}
                            type="file"
                            accept=".gpx"
                            onBlur={onBlur}
                            onChange={(e) => {
                              const f = e.target.files?.[0] ?? null;
                              onChange(f);
                              setPendingFile(f);
                              setErrorMessage(null);
                            }}
                            className={cn(
                              "min-h-12 w-full rounded-lg bg-white px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                              "shadow-ring",
                            )}
                            aria-invalid={errors.file ? true : undefined}
                            data-testid="variant-upload-file"
                          />
                        )}
                      />
                      {errors.file && (
                        <p className="text-xs text-red-600" role="alert">
                          Selecciona un archivo GPX válido.
                        </p>
                      )}
                    </div>
                  </>
                )}

                {stage === "laps-input" && (
                  <div className="space-y-1">
                    <label
                      htmlFor="variant-upload-recorded-laps"
                      className="block text-xs font-medium text-mid-gray"
                    >
                      Vueltas grabadas
                    </label>
                    <input
                      id="variant-upload-recorded-laps"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={20}
                      {...register("recorded_laps", {
                        setValueAs: (v) =>
                          v === "" || v === null || v === undefined
                            ? undefined
                            : Number(v),
                      })}
                      className={cn(
                        "min-h-12 w-full rounded-lg bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                        "shadow-ring",
                      )}
                      aria-invalid={errors.recorded_laps ? true : undefined}
                      data-testid="variant-upload-recorded-laps"
                    />
                    {errors.recorded_laps && (
                      <p className="text-xs text-red-600" role="alert">
                        {errors.recorded_laps.message}
                      </p>
                    )}
                  </div>
                )}

                {errorMessage && (
                  <p
                    className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
                    role="alert"
                    data-testid="variant-upload-error"
                  >
                    {errorMessage}
                  </p>
                )}
              </>
            )}

            {stage === "question" && detectionInfo && (
              <div
                className="space-y-3 rounded-lg bg-light-gray/40 px-4 py-3 text-sm text-charcoal ring-1 ring-[rgba(34,42,53,0.08)]"
                role="status"
                data-testid="variant-upload-question"
              >
                <p>
                  {detectionInfo.detection.method === "closed_loop"
                    ? closedLoopQuestion(detectionInfo)
                    : manualQuestion(detectionInfo)}
                </p>
              </div>
            )}

            {stage === "success" && detectionInfo && (
              <div
                className="flex items-start gap-2 rounded-lg bg-light-gray/40 px-4 py-3 text-sm text-charcoal ring-1 ring-[rgba(34,42,53,0.08)]"
                role="status"
                data-testid="variant-upload-success"
              >
                <CheckCircle2
                  size={16}
                  aria-hidden="true"
                  className="mt-0.5 shrink-0"
                />
                <span>{successMessage(detectionInfo)}</span>
              </div>
            )}
          </form>
        </SheetBody>

        <SheetFooter>
          {stage === "form" && (
            <>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="min-h-12 rounded-lg px-4 text-sm font-medium text-mid-gray hover:text-charcoal"
              >
                Cancelar
              </button>
              <button
                type="submit"
                form="variant-upload-form"
                disabled={isPending}
                className="inline-flex min-h-12 items-center gap-2 rounded-lg bg-charcoal px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                data-testid="variant-upload-submit"
              >
                {isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Subir GPX
              </button>
            </>
          )}

          {stage === "question" && (
            <>
              <button
                type="button"
                onClick={() => setStage("laps-input")}
                className="min-h-12 rounded-lg px-4 text-sm font-medium text-mid-gray hover:text-charcoal"
                data-testid="variant-upload-indicate-laps"
              >
                No, indicar vueltas
              </button>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="min-h-12 rounded-lg bg-charcoal px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                data-testid="variant-upload-confirm"
              >
                Sí, guardar
              </button>
            </>
          )}

          {stage === "laps-input" && (
            <button
              type="submit"
              form="variant-upload-form"
              disabled={isPending || watchedRecordedLaps == null}
              className="inline-flex min-h-12 items-center gap-2 rounded-lg bg-charcoal px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              data-testid="variant-upload-laps-submit"
            >
              {isPending && (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              )}
              Guardar vueltas
            </button>
          )}

          {stage === "success" && (
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="min-h-12 rounded-lg bg-charcoal px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              data-testid="variant-upload-close"
            >
              Cerrar
            </button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
