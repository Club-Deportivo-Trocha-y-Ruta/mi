/**
 * EditConditionsDialog — Sheet lateral para editar condiciones de carrera.
 *
 * Usado desde RaceConditionsCard (tri-estado: Vacío / Parcial / Completo).
 * Precarga los valores actuales del evento. Submit vía useUpdateRaceEventConditions.
 *
 * Toast de éxito/error: banner <div role="status"> sin librería externa,
 * patrón establecido en UnlinkedCompetitorsTab.
 *
 * Privacidad: solo metadatos logísticos de jornadas — sin datos de menores.
 */
import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { z } from "zod";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from "@/components/ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useUpdateRaceEventConditions } from "@/hooks/race/useRaceEventConditions";
import { cn } from "@/lib/utils";
import {
  SURFACE_CONDITIONS,
  SURFACE_CONDITION_LABELS,
} from "@/types/raceEvents.types";
import type {
  RaceEventConditions,
  SurfaceCondition,
} from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Zod schema — mismas reglas que F3 del wizard
// ---------------------------------------------------------------------------

const editConditionsSchema = z.object({
  climate: z
    .string()
    .max(60, "Máximo 60 caracteres")
    .optional()
    .or(z.literal("")),
  temperature_c: z
    .union([z.string(), z.number()])
    .optional()
    .nullable()
    .refine(
      (v) => {
        if (v === null || v === undefined || v === "") return true;
        const n = typeof v === "number" ? v : parseFloat(v as string);
        return !isNaN(n) && n >= 0 && n <= 50;
      },
      { message: "Debe estar entre 0 y 50 °C" },
    ),
  surface_condition: z
    .enum(["seca", "humeda", "barro", "lluvia", "mixta"] as const)
    .optional()
    .nullable(),
  altitude_msnm: z
    .union([z.string(), z.number()])
    .optional()
    .nullable()
    .refine(
      (v) => {
        if (v === null || v === undefined || v === "") return true;
        const n = typeof v === "number" ? v : parseFloat(v as string);
        return !isNaN(n) && n >= 0 && n <= 5000;
      },
      { message: "Debe estar entre 0 y 5000 msnm" },
    ),
  weather_notes: z
    .string()
    .max(2000, "Máximo 2000 caracteres")
    .optional()
    .or(z.literal("")),
});

type EditConditionsValues = z.infer<typeof editConditionsSchema>;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditConditionsDialogProps {
  raceEventId: number;
  currentConditions: Partial<RaceEventConditions>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EditConditionsDialog({
  raceEventId,
  currentConditions,
  open,
  onOpenChange,
}: EditConditionsDialogProps) {
  const updateMutation = useUpdateRaceEventConditions();
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Precarga valores actuales al abrir el sheet
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<EditConditionsValues>({
    resolver: zodResolver(editConditionsSchema),
    defaultValues: buildDefaults(currentConditions),
  });

  // Re-sincronizar defaultValues cuando el sheet se abre con datos nuevos
  useEffect(() => {
    if (open) {
      reset(buildDefaults(currentConditions));
      setToast(null);
    }
  }, [open, currentConditions, reset]);

  const onSubmit = (values: EditConditionsValues) => {
    // Normalizar strings vacíos → null antes de enviar
    const body = {
      climate: strOrNull(values.climate),
      temperature_c: values.temperature_c === "" ? null : values.temperature_c,
      surface_condition: values.surface_condition ?? null,
      altitude_msnm:
        values.altitude_msnm === "" || values.altitude_msnm === undefined
          ? null
          : typeof values.altitude_msnm === "string"
            ? parseFloat(values.altitude_msnm) || null
            : (values.altitude_msnm ?? null),
      weather_notes: strOrNull(values.weather_notes),
    };

    updateMutation.mutate(
      { raceEventId, body },
      {
        onSuccess: () => {
          setToast({ type: "success", message: "Condiciones guardadas correctamente." });
          // Cierra el sheet tras 1.2 s para que el usuario vea el feedback
          setTimeout(() => onOpenChange(false), 1200);
        },
        onError: () => {
          setToast({
            type: "error",
            message: "No se pudieron guardar las condiciones. Intenta de nuevo.",
          });
        },
      },
    );
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="max-w-md">
        <SheetHeader>
          <SheetTitle>Condiciones de carrera</SheetTitle>
          <SheetDescription>
            Edita las condiciones del evento. Todos los campos son opcionales.
          </SheetDescription>
        </SheetHeader>

        <SheetBody>
          <form
            id="edit-conditions-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-5"
            noValidate
          >
            {/* Temperatura + Superficie */}
            <div className="grid gap-4 sm:grid-cols-2">
              {/* Temperatura */}
              <div className="space-y-1">
                <label
                  htmlFor="ec-temperature"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Temperatura
                </label>
                <div className="relative">
                  <input
                    id="ec-temperature"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    max={50}
                    step={0.1}
                    {...register("temperature_c")}
                    className={cn(
                      "w-full rounded-lg bg-white py-3 pl-3 pr-12 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px]",
                    )}
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                    aria-invalid={errors.temperature_c ? true : undefined}
                  />
                  <span
                    className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-mid-gray"
                    aria-hidden="true"
                  >
                    °C
                  </span>
                </div>
                {errors.temperature_c && (
                  <p className="text-xs text-red-600" role="alert">
                    {errors.temperature_c.message}
                  </p>
                )}
              </div>

              {/* Altitud */}
              <div className="space-y-1">
                <label
                  htmlFor="ec-altitude"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Altitud
                </label>
                <div className="relative">
                  <input
                    id="ec-altitude"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    max={5000}
                    step={1}
                    {...register("altitude_msnm")}
                    className={cn(
                      "w-full rounded-lg bg-white py-3 pl-3 pr-14 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                      "min-h-[48px]",
                    )}
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                    aria-invalid={errors.altitude_msnm ? true : undefined}
                  />
                  <span
                    className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-mid-gray"
                    aria-hidden="true"
                  >
                    msnm
                  </span>
                </div>
                {errors.altitude_msnm && (
                  <p className="text-xs text-red-600" role="alert">
                    {errors.altitude_msnm.message}
                  </p>
                )}
              </div>
            </div>

            {/* Condición de superficie — ToggleGroup chips */}
            <div className="space-y-2">
              <span className="block text-xs font-medium text-mid-gray">
                Condición del terreno
              </span>
              <Controller
                name="surface_condition"
                control={control}
                render={({ field }) => (
                  <ToggleGroup
                    type="single"
                    value={field.value ?? ""}
                    onValueChange={(v) =>
                      field.onChange(
                        v === "" ? null : (v as SurfaceCondition),
                      )
                    }
                    className="flex flex-wrap gap-2"
                    aria-label="Condición del terreno"
                  >
                    {SURFACE_CONDITIONS.map((sc) => (
                      <ToggleGroupItem
                        key={sc}
                        value={sc}
                        aria-label={SURFACE_CONDITION_LABELS[sc]}
                        className="min-h-[48px] min-w-[72px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-2 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white"
                      >
                        {SURFACE_CONDITION_LABELS[sc]}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                )}
              />
            </div>

            {/* Clima */}
            <div className="space-y-1">
              <label
                htmlFor="ec-climate"
                className="block text-xs font-medium text-mid-gray"
              >
                Clima
              </label>
              <input
                id="ec-climate"
                type="text"
                list="ec-climate-suggestions"
                placeholder="ej: soleado, parcialmente nublado"
                maxLength={60}
                {...register("climate")}
                className={cn(
                  "w-full rounded-lg bg-white px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                  "min-h-[48px]",
                )}
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                aria-invalid={errors.climate ? true : undefined}
              />
              <datalist id="ec-climate-suggestions">
                <option value="Soleado" />
                <option value="Parcialmente nublado" />
                <option value="Nublado" />
                <option value="Llovizna" />
                <option value="Lluvioso" />
                <option value="Ventoso" />
                <option value="Soleado con viento" />
              </datalist>
              {errors.climate && (
                <p className="text-xs text-red-600" role="alert">
                  {errors.climate.message}
                </p>
              )}
            </div>

            {/* Notas de clima */}
            <div className="space-y-1">
              <label
                htmlFor="ec-weather-notes"
                className="block text-xs font-medium text-mid-gray"
              >
                Notas adicionales
              </label>
              <textarea
                id="ec-weather-notes"
                rows={3}
                maxLength={2000}
                placeholder="Condiciones generales del trazado y clima — evite incluir nombres de atletas o información médica"
                {...register("weather_notes")}
                className="w-full resize-y rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{
                  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
                  minHeight: "80px",
                }}
                aria-invalid={errors.weather_notes ? true : undefined}
              />
              {errors.weather_notes && (
                <p className="text-xs text-red-600" role="alert">
                  {errors.weather_notes.message}
                </p>
              )}
            </div>

            {/* Toast inline */}
            {toast && (
              <div
                role="status"
                aria-live="polite"
                className={cn(
                  "flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
                  toast.type === "success"
                    ? "border border-emerald-200 bg-emerald-50 text-emerald-900"
                    : "border border-red-200 bg-red-50 text-red-800",
                )}
              >
                {toast.type === "success" ? (
                  <CheckCircle2 size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                ) : (
                  <XCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                )}
                <span>{toast.message}</span>
              </div>
            )}
          </form>
        </SheetBody>

        <SheetFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-lg px-4 py-2 text-sm font-medium text-mid-gray hover:text-charcoal"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="edit-conditions-form"
            disabled={updateMutation.isPending}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {updateMutation.isPending && (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            )}
            Guardar
          </button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function strOrNull(v: string | undefined | null): string | null {
  if (!v || v.trim() === "") return null;
  return v.trim();
}

function buildDefaults(
  c: Partial<RaceEventConditions>,
): EditConditionsValues {
  return {
    climate: c.climate ?? "",
    temperature_c: c.temperature_c ?? "",
    surface_condition: c.surface_condition ?? null,
    altitude_msnm: c.altitude_msnm != null ? String(c.altitude_msnm) : "",
    weather_notes: c.weather_notes ?? "",
  };
}
