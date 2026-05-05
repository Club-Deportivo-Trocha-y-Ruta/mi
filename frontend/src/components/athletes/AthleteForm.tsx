import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { computeAgeDecimal, getCategory } from "@/lib/category";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athleteFormSchema = z.object({
  first_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
  last_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
  birth_date: z
    .string()
    .min(1, "Fecha requerida")
    .refine((value) => value < new Date().toISOString().slice(0, 10), "No puede ser futura ni hoy")
    .refine((value) => value >= "1990-01-01", "Fecha mínima 1990-01-01"),
  sex: z.nativeEnum(Sex),
  club_join_date: z
    .string()
    .optional()
    .refine(
      (v) => !v || v <= new Date().toISOString().slice(0, 10),
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

const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 disabled:bg-light-gray disabled:text-mid-gray";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

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
      className="space-y-5 rounded-xl bg-white p-5"
      style={{ boxShadow: "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px" }}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-sm font-medium text-charcoal">
          Nombres
          <input
            className={inputClass}
            style={inputStyle}
            {...form.register("first_name")}
          />
          <span className="text-xs text-red-600">{form.formState.errors.first_name?.message}</span>
        </label>
        <label className="text-sm font-medium text-charcoal">
          Apellidos
          <input
            className={inputClass}
            style={inputStyle}
            {...form.register("last_name")}
          />
          <span className="text-xs text-red-600">{form.formState.errors.last_name?.message}</span>
        </label>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <label className="text-sm font-medium text-charcoal">
          Fecha de nacimiento
          <input
            type="date"
            className={inputClass}
            style={inputStyle}
            autoComplete="off"
            max={new Date(Date.now() - 86400000).toISOString().slice(0, 10)}
            {...form.register("birth_date")}
            disabled={mode === "edit"}
          />
          <span className="text-xs text-red-600">{form.formState.errors.birth_date?.message}</span>
        </label>
        <label className="text-sm font-medium text-charcoal">
          Sexo
          <select
            className={inputClass}
            style={inputStyle}
            {...form.register("sex")}
            disabled={mode === "edit"}
          >
            <option value={Sex.M}>M</option>
            <option value={Sex.F}>F</option>
          </select>
        </label>
        <label className="text-sm font-medium text-charcoal">
          Fecha ingreso al club
          <input
            type="date"
            className={inputClass}
            style={inputStyle}
            max={new Date().toISOString().slice(0, 10)}
            {...form.register("club_join_date")}
          />
          <span className="text-xs text-red-600">
            {form.formState.errors.club_join_date?.message}
          </span>
        </label>
      </div>

      {computed && (
        <p className="rounded-lg bg-light-gray px-3 py-2.5 text-sm text-mid-gray">
          Edad estimada: <span className="font-medium text-charcoal">{computed.age_decimal.toFixed(1)} años</span>
          {" | "}
          Categoría: <span className="font-medium text-charcoal">{computed.category}</span>
        </p>
      )}

      {submitError && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{submitError}</p>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50"
        style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
      >
        {isSubmitting ? "Guardando..." : mode === "create" ? "Crear atleta" : "Guardar cambios"}
      </button>
    </form>
  );
}
