/**
 * EditCourseDescriptionDialog — Sheet lateral para editar la descripción
 * cualitativa del circuito de una válida (feature 043, US3).
 *
 * Mismo patrón que `EditConditionsDialog.tsx`: precarga los valores actuales,
 * RHF + Zod (`descriptionSchema`, ya existente), toast inline de éxito/error,
 * `noValidate` (sin burbujas HTML5 — Zod es la única fuente de mensajes de
 * error visibles al usuario).
 *
 * Privacidad: `course_notes` es texto libre sobre el trazado — el placeholder
 * ya advierte no incluir nombres de atletas ni información médica, igual que
 * `weather_notes` en `EditConditionsDialog`.
 */
import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { z } from "zod";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetFooter,
} from "@/components/ui/sheet";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useUpdateCourseDescription } from "@/hooks/race/useRaceCourse";
import { getCourseErrorMessage } from "@/lib/courseErrors";
import { cn } from "@/lib/utils";
import { descriptionSchema } from "@/schemas/raceCourse";
import type { DescriptionFormValues } from "@/schemas/raceCourse";
import {
  KEY_SECTOR_LABELS,
  TERRAIN_TYPE_LABELS,
} from "@/types/raceCourse.types";
import type {
  CourseDescription,
  CourseDescriptionUpdateBody,
  KeySector,
  TerrainType,
} from "@/types/raceCourse.types";

// ---------------------------------------------------------------------------
// Catálogos locales de UI
// ---------------------------------------------------------------------------

const TERRAIN_TYPES = Object.keys(TERRAIN_TYPE_LABELS) as TerrainType[];
const KEY_SECTORS = Object.keys(KEY_SECTOR_LABELS) as KeySector[];

/** Etiquetas exactas de `ui-course.md` §2. */
const DIFFICULTY_OPTIONS: Array<{ value: 1 | 2 | 3 | 4 | 5; label: string }> = [
  { value: 1, label: "1 — Muy fácil" },
  { value: 2, label: "2 — Fácil" },
  { value: 3, label: "3 — Media" },
  { value: 4, label: "4 — Técnico" },
  { value: 5, label: "5 — Muy técnico" },
];

const UNSET = "unset" as const;

// `technical_difficulty` uses `z.coerce.number()`, whose Zod *input* type is
// `unknown` (raw, pre-coercion value) while its *output* type is
// `number | null | undefined` (`DescriptionFormValues`, the type this
// component works with everywhere else). RHF needs both: the form's input
// shape for `useForm`/`Controller` field typing, and the resolver's output
// shape for what `handleSubmit`'s callback receives.
type DescriptionFormInput = z.input<typeof descriptionSchema>;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditCourseDescriptionDialogProps {
  raceEventId: number;
  currentDescription: Partial<CourseDescription> | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EditCourseDescriptionDialog({
  raceEventId,
  currentDescription,
  open,
  onOpenChange,
}: EditCourseDescriptionDialogProps) {
  const updateMutation = useUpdateCourseDescription();
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors },
  } = useForm<DescriptionFormInput, unknown, DescriptionFormValues>({
    resolver: zodResolver(descriptionSchema),
    defaultValues: buildDefaults(currentDescription),
  });

  // Re-sincronizar defaultValues cuando el sheet se abre con datos nuevos.
  useEffect(() => {
    if (open) {
      reset(buildDefaults(currentDescription));
      setToast(null);
    }
  }, [open, currentDescription, reset]);

  const notesValue = watch("course_notes") ?? "";

  const onSubmit = (values: DescriptionFormValues) => {
    // Se reenvía el estado completo del formulario en cada guardado — el
    // frontend siempre conoce su propio estado actual, así que no hace falta
    // calcular un diff cliente-side (el backend soporta reenviar campos sin
    // cambios sin efecto adicional).
    const body: CourseDescriptionUpdateBody = {
      terrain_type: values.terrain_type ?? null,
      technical_difficulty: values.technical_difficulty ?? null,
      key_sectors: values.key_sectors ?? [],
      course_notes: strOrNull(values.course_notes),
    };

    updateMutation.mutate(
      { raceEventId, body },
      {
        onSuccess: () => {
          setToast({
            type: "success",
            message: "Descripción del circuito guardada correctamente.",
          });
          // Cierra el sheet tras 1.2 s para que el usuario vea el feedback.
          setTimeout(() => onOpenChange(false), 1200);
        },
        onError: (err) => {
          setToast({
            type: "error",
            message: getCourseErrorMessage(
              err,
              "No se pudo guardar la descripción. Intenta de nuevo.",
            ),
          });
        },
      },
    );
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="max-w-md">
        <SheetHeader>
          <SheetTitle>Descripción del circuito</SheetTitle>
          <SheetDescription>
            Describe el trazado para el equipo y las familias. Todos los
            campos son opcionales.
          </SheetDescription>
        </SheetHeader>

        <SheetBody>
          <form
            id="edit-course-description-form"
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-5"
            noValidate
          >
            {/* Terreno — ToggleGroup chips */}
            <div className="space-y-2">
              <span className="block text-xs font-medium text-mid-gray">
                Tipo de superficie
              </span>
              <Controller
                name="terrain_type"
                control={control}
                render={({ field }) => (
                  <ToggleGroup
                    type="single"
                    value={field.value ?? UNSET}
                    onValueChange={(v) =>
                      field.onChange(
                        v === "" || v === UNSET ? null : (v as TerrainType),
                      )
                    }
                    className="flex flex-wrap gap-2"
                    aria-label="Tipo de superficie"
                  >
                    {TERRAIN_TYPES.map((t) => (
                      <ToggleGroupItem
                        key={t}
                        value={t}
                        aria-label={TERRAIN_TYPE_LABELS[t]}
                        className="min-h-[48px] min-w-[72px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-2 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-surface"
                      >
                        {TERRAIN_TYPE_LABELS[t]}
                      </ToggleGroupItem>
                    ))}
                    <ToggleGroupItem
                      value={UNSET}
                      aria-label="Sin especificar terreno"
                      className="min-h-[48px] min-w-[72px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-surface"
                    >
                      Sin especificar
                    </ToggleGroupItem>
                  </ToggleGroup>
                )}
              />
              {errors.terrain_type && (
                <p className="text-xs text-red-600" role="alert">
                  {errors.terrain_type.message}
                </p>
              )}
            </div>

            {/* Dificultad técnica — RadioGroup */}
            <div className="space-y-2">
              <span className="block text-xs font-medium text-mid-gray">
                Dificultad técnica
              </span>
              <Controller
                name="technical_difficulty"
                control={control}
                render={({ field }) => (
                  <RadioGroup
                    value={field.value != null ? String(field.value) : UNSET}
                    onValueChange={(v) =>
                      field.onChange(v === UNSET ? null : Number(v))
                    }
                    aria-label="Dificultad técnica"
                    className="gap-2"
                  >
                    {DIFFICULTY_OPTIONS.map((opt) => (
                      <label
                        key={opt.value}
                        htmlFor={`ecd-difficulty-${opt.value}`}
                        className="flex min-h-[48px] cursor-pointer items-center gap-2 rounded-lg px-2 hover:bg-light-gray"
                      >
                        <RadioGroupItem
                          value={String(opt.value)}
                          id={`ecd-difficulty-${opt.value}`}
                        />
                        <span className="text-sm text-charcoal">
                          {opt.label}
                        </span>
                      </label>
                    ))}
                    <label
                      htmlFor="ecd-difficulty-unset"
                      className="flex min-h-[48px] cursor-pointer items-center gap-2 rounded-lg px-2 hover:bg-light-gray"
                    >
                      <RadioGroupItem value={UNSET} id="ecd-difficulty-unset" />
                      <span className="text-sm text-mid-gray">
                        Sin especificar
                      </span>
                    </label>
                  </RadioGroup>
                )}
              />
              {errors.technical_difficulty && (
                <p className="text-xs text-red-600" role="alert">
                  {errors.technical_difficulty.message}
                </p>
              )}
            </div>

            {/* Sectores clave — checkboxes, >=48px tap target cada uno */}
            <fieldset className="space-y-2">
              <legend className="block text-xs font-medium text-mid-gray">
                Sectores clave
              </legend>
              <Controller
                name="key_sectors"
                control={control}
                render={({ field }) => {
                  const selected = field.value ?? [];
                  return (
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {KEY_SECTORS.map((sector) => {
                        const checked = selected.includes(sector);
                        return (
                          <label
                            key={sector}
                            className="flex min-h-[48px] cursor-pointer items-center gap-2 rounded-lg px-2 hover:bg-light-gray"
                          >
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(next) => {
                                if (next) {
                                  field.onChange([...selected, sector]);
                                } else {
                                  field.onChange(
                                    selected.filter((s) => s !== sector),
                                  );
                                }
                              }}
                              aria-label={KEY_SECTOR_LABELS[sector]}
                            />
                            <span className="text-sm text-charcoal">
                              {KEY_SECTOR_LABELS[sector]}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  );
                }}
              />
              {errors.key_sectors && (
                <p className="text-xs text-red-600" role="alert">
                  {errors.key_sectors.message}
                </p>
              )}
            </fieldset>

            {/* Notas */}
            <div className="space-y-1">
              <div className="flex items-baseline justify-between">
                <label
                  htmlFor="ecd-notes"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Notas
                </label>
                <span
                  className="text-[11px] text-mid-gray"
                  data-testid="ecd-notes-counter"
                >
                  {notesValue.length}/1000
                </span>
              </div>
              <textarea
                id="ecd-notes"
                rows={4}
                maxLength={1000}
                placeholder="Características fijas del trazado (sombra, saltos, zonas de adelantamiento) — evite incluir nombres de atletas o información médica"
                {...register("course_notes")}
                className={cn(
                  "w-full resize-y rounded-lg bg-surface-raised px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                  "shadow-ring",
                )}
                style={{ minHeight: "100px" }}
                aria-invalid={errors.course_notes ? true : undefined}
              />
              {errors.course_notes && (
                <p className="text-xs text-red-600" role="alert">
                  {errors.course_notes.message}
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
            className="inline-flex min-h-[48px] items-center rounded-lg px-4 py-2 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="edit-course-description-form"
            disabled={updateMutation.isPending}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90 disabled:opacity-50"
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
  d: Partial<CourseDescription> | null | undefined,
): DescriptionFormValues {
  return {
    terrain_type: d?.terrain_type ?? null,
    technical_difficulty: d?.technical_difficulty ?? null,
    key_sectors: d?.key_sectors ?? [],
    course_notes: d?.course_notes ?? "",
  };
}
