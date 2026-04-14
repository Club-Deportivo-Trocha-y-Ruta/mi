import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { computeAgeDecimal, getCategory } from "@/lib/category";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athleteFormSchema = z.object({
  first_name: z.string().trim().min(2, "Minimo 2 caracteres"),
  last_name: z.string().trim().min(2, "Minimo 2 caracteres"),
  birth_date: z
    .string()
    .min(1, "Fecha requerida")
    .refine((value) => new Date(value).getTime() <= Date.now(), "No puede ser futura")
    .refine((value) => value >= "1990-01-01", "Fecha minima 1990-01-01"),
  sex: z.nativeEnum(Sex),
  club_join_date: z
    .string()
    .optional()
    .refine(
      (v) => !v || new Date(v).getTime() <= Date.now(),
      "No puede ser futura",
    ),
});

export type AthleteFormValues = z.output<typeof athleteFormSchema>;

interface AthleteFormProps {
  initialValues?: AthleteDetailOut;
  mode: "create" | "edit";
  isSubmitting: boolean;
  submitError: string | null;
  onSubmit: (values: AthleteFormValues) => void;
}

export function AthleteForm({
  initialValues,
  mode,
  isSubmitting,
  submitError,
  onSubmit,
}: AthleteFormProps) {
  const form = useForm<z.input<typeof athleteFormSchema>, unknown, AthleteFormValues>({
    resolver: zodResolver(athleteFormSchema),
    defaultValues: {
      first_name: initialValues?.first_name ?? "",
      last_name: initialValues?.last_name ?? "",
      birth_date: initialValues?.birth_date ?? "",
      sex: initialValues?.sex ?? Sex.M,
      club_join_date: initialValues?.club_join_date ?? "",
    },
  });

  const birthDate = form.watch("birth_date");
  const sex = form.watch("sex");

  useEffect(() => {
    if (!initialValues) return;
    form.reset({
      first_name: initialValues.first_name,
      last_name: initialValues.last_name,
      birth_date: initialValues.birth_date,
      sex: initialValues.sex,
      club_join_date: initialValues.club_join_date ?? "",
    });
  }, [form, initialValues]);

  const computed = useMemo(() => {
    if (!birthDate) return null;
    const parsed = new Date(`${birthDate}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) return null;
    return {
      age_decimal: computeAgeDecimal(parsed),
      category: getCategory(parsed.getFullYear(), sex),
    };
  }, [birthDate, sex]);

  return (
    <form
      onSubmit={form.handleSubmit(onSubmit)}
      className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
    >
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-sm text-slate-700">
          Nombres
          <input
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            {...form.register("first_name")}
          />
          <span className="text-xs text-rose-600">{form.formState.errors.first_name?.message}</span>
        </label>
        <label className="text-sm text-slate-700">
          Apellidos
          <input
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            {...form.register("last_name")}
          />
          <span className="text-xs text-rose-600">{form.formState.errors.last_name?.message}</span>
        </label>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <label className="text-sm text-slate-700">
          Fecha de nacimiento
          <input
            type="date"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            {...form.register("birth_date")}
            disabled={mode === "edit"}
          />
          <span className="text-xs text-rose-600">{form.formState.errors.birth_date?.message}</span>
        </label>
        <label className="text-sm text-slate-700">
          Sexo
          <select
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            {...form.register("sex")}
            disabled={mode === "edit"}
          >
            <option value={Sex.M}>M</option>
            <option value={Sex.F}>F</option>
          </select>
        </label>
        <label className="text-sm text-slate-700">
          Fecha ingreso al club
          <input
            type="date"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            {...form.register("club_join_date")}
          />
          <span className="text-xs text-rose-600">
            {form.formState.errors.club_join_date?.message}
          </span>
        </label>
      </div>

      {computed && (
        <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Edad estimada: {computed.age_decimal.toFixed(1)} anos | Categoria: {computed.category}
        </p>
      )}

      {submitError && <p className="text-sm text-rose-600">{submitError}</p>}

      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800 disabled:opacity-60"
      >
        {isSubmitting ? "Guardando..." : mode === "create" ? "Crear atleta" : "Guardar cambios"}
      </button>
    </form>
  );
}
