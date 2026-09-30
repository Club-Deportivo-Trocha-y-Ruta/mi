/**
 * ImdertyProfileForm — campos editables del perfil IMDERTY de un atleta
 * (feature 047, US2): división de apellidos, documento, dirección, barrio,
 * institución/grado, EPS y teléfono propio.
 *
 * Contrato: `PUT /api/athletes/{athlete_id}/imderty-profile` — el body es
 * `ImdertyProfileUpdateValues` (`schemas/imderty.ts`), la respuesta trae el
 * perfil actualizado más `warnings` (hoy solo `duplicate_document_in_club`,
 * un aviso no bloqueante — FR-004). Los 422 de validación (documento con
 * letras en R.C/T.I/C.C, `barrio_id` junto con `other_municipality=true`,
 * una división confirmada que no reconstruye `last_name`) se muestran como
 * errores inline en español, no como toast.
 *
 * Layout: ancho máximo `max-w-4xl`; una columna a 360 px, dos desde 768 px
 * (`md:`) y tres desde 1024 px (`lg:`) en las filas de campos cortos; la barra de guardar queda pegada (`sticky bottom-0`) al fondo del
 * contenedor para que sea alcanzable sin desplazar el formulario entero en
 * pantallas cortas.
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BarrioCombobox, type BarrioComboboxValue } from "@/components/imderty/BarrioCombobox";
import { SurnameSplitConfirm } from "@/components/imderty/SurnameSplitConfirm";
import { useUpdateImdertyProfile } from "@/hooks/useImderty";
import {
  imdertyDocumentTypeLabels,
  imdertyDocumentTypes,
  imdertyGradeLabels,
  imdertyGrades,
  imdertyProfileUpdateSchema,
  type ImdertyProfile,
  type ImdertyProfileUpdateValues,
} from "@/schemas/imderty";

export interface ImdertyProfileFormProps {
  athleteId: number;
  profile: ImdertyProfile;
}

/** Documentos que la planilla exige numéricos (FR-004). */
const NUMERIC_DOCUMENT_TYPES = new Set(["rc", "ti", "cc"]);
/** Sentinela de los `<Select>` opcionales — nunca viaja al backend. */
const NONE_VALUE = "__none__";

const profileFormSchema = imdertyProfileUpdateSchema.superRefine((data, ctx) => {
  if (
    data.document_type &&
    NUMERIC_DOCUMENT_TYPES.has(data.document_type) &&
    data.document_number &&
    !/^\d+$/.test(data.document_number)
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["document_number"],
      message: "Solo dígitos para R.C, T.I y C.C",
    });
  }
});

type ProfileFormValues = ImdertyProfileUpdateValues;
/** Tipo de entrada de RHF (pre-`zodResolver`): `confirm_surname_split` es
 * opcional acá porque su `.default(false)` solo se aplica en la salida —
 * lo exporta `SurnameSplitConfirm` para tipar su prop `control`. */
export type ProfileFormInputValues = z.input<typeof profileFormSchema>;

function defaultsFromProfile(profile: ImdertyProfile): ProfileFormValues {
  return {
    first_surname: profile.first_surname ?? profile.surname_split.proposed_first ?? null,
    second_surname: profile.second_surname ?? profile.surname_split.proposed_second ?? null,
    confirm_surname_split: profile.surname_split.confirmed,
    document_type: profile.document_type,
    document_number: profile.document_number,
    address: profile.address,
    barrio_id: profile.barrio?.id ?? null,
    other_municipality: profile.other_municipality,
    school: profile.school,
    grade: profile.grade,
    eps: profile.eps,
    phone: profile.phone,
  };
}

/** Extrae un mensaje de error legible para el PUT del perfil. */
function getProfileErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const e = err as { response?: { data?: { detail?: unknown }; status?: number } };
    if (e.response?.status === 403) return "Sin permiso para editar este perfil.";
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return "No fue posible guardar el perfil. Intenta de nuevo.";
}

export function ImdertyProfileForm({ athleteId, profile }: ImdertyProfileFormProps) {
  const updateProfile = useUpdateImdertyProfile(athleteId);
  const [warnings, setWarnings] = React.useState<string[]>([]);

  // `confirm_surname_split` lleva `.default(false)` en el schema del
  // contrato: su tipo de entrada (antes de resolver) es opcional, pero el
  // de salida (tras aplicar el default) es obligatorio — mismo patrón que
  // `AthleteForm.tsx` para reconciliar `z.input`/`z.output` con RHF.
  const form = useForm<ProfileFormInputValues, unknown, ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    values: defaultsFromProfile(profile),
  });

  const barrioId = form.watch("barrio_id");
  const otherMunicipality = form.watch("other_municipality");
  const barrioValue: BarrioComboboxValue = {
    barrioId: barrioId ?? null,
    otherMunicipality: otherMunicipality ?? false,
  };

  function handleBarrioChange(next: BarrioComboboxValue) {
    form.setValue("barrio_id", next.barrioId, { shouldDirty: true, shouldValidate: true });
    form.setValue("other_municipality", next.otherMunicipality, {
      shouldDirty: true,
      shouldValidate: true,
    });
  }

  function onSubmit(values: ProfileFormValues) {
    setWarnings([]);
    updateProfile.mutate(values, {
      onSuccess: (response) => {
        toast.success("Perfil IMDERTY actualizado.");
        setWarnings(response.warnings);
      },
      onError: (err) => {
        toast.error(getProfileErrorMessage(err));
      },
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="max-w-4xl space-y-5">
        <SurnameSplitConfirm
          control={form.control}
          proposedFirst={profile.surname_split.proposed_first}
          proposedSecond={profile.surname_split.proposed_second}
          alreadyConfirmed={profile.surname_split.confirmed}
        />

        {warnings.includes("duplicate_document_in_club") && (
          <Alert variant="warning">
            <AlertTitle>Documento duplicado</AlertTitle>
            <AlertDescription>
              Este número de documento ya está registrado en otro atleta del club. Se guardó
              igual — conviene revisarlo.
            </AlertDescription>
          </Alert>
        )}

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <FormField
            control={form.control}
            name="document_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Tipo de documento</FormLabel>
                <Select
                  value={field.value ?? NONE_VALUE}
                  onValueChange={(value) => field.onChange(value === NONE_VALUE ? null : value)}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value={NONE_VALUE}>Sin especificar</SelectItem>
                    {imdertyDocumentTypes.map((value) => (
                      <SelectItem key={value} value={value}>
                        {imdertyDocumentTypeLabels[value]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="document_number"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Número de documento</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    inputMode="numeric"
                    autoComplete="off"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="phone"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Teléfono del atleta</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    inputMode="numeric"
                    autoComplete="off"
                  />
                </FormControl>
                <FormDescription>
                  Si está vacío, se usa el teléfono del contacto principal.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="address"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Dirección</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value ?? ""} autoComplete="off" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <BarrioCombobox label="Barrio" value={barrioValue} onChange={handleBarrioChange} />
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <FormField
            control={form.control}
            name="school"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Institución / colegio / grupo / club</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    placeholder="Ej.: Colegio o club donde estudia"
                    autoComplete="off"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="grade"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Grado</FormLabel>
                <Select
                  value={field.value ?? NONE_VALUE}
                  onValueChange={(value) => field.onChange(value === NONE_VALUE ? null : value)}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value={NONE_VALUE}>Sin especificar</SelectItem>
                    {imdertyGrades.map((value) => (
                      <SelectItem key={value} value={value}>
                        {imdertyGradeLabels[value]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="eps"
            render={({ field }) => (
              <FormItem>
                <FormLabel>EPS</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value ?? ""} autoComplete="off" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

        </div>

        <div className="sticky bottom-0 -mx-5 border-t border-hairline bg-surface-raised/95 px-5 py-3 backdrop-blur">
          <Button type="submit" disabled={updateProfile.isPending} className="w-full sm:w-auto">
            {updateProfile.isPending && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Guardar perfil
          </Button>
        </div>
      </form>
    </Form>
  );
}
