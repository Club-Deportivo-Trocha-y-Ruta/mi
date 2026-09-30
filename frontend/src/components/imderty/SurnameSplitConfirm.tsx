/**
 * SurnameSplitConfirm — bloque de confirmación de la división de apellidos
 * del perfil IMDERTY (feature 047, US2, FR-001a).
 *
 * `athletes.last_name` sigue siendo el texto completo (research.md R7); el
 * perfil IMDERTY agrega `first_surname`/`second_surname` por separado. Para
 * un atleta ya existente, el backend propone una división una sola vez
 * (`surname_split.proposed_first/proposed_second`) y el coach la confirma o
 * la corrige — nada cambia sin esa confirmación explícita (checkbox
 * `confirm_surname_split`). Mientras no esté confirmada, la planilla usa el
 * apellido sin dividir y el panel de disponibilidad marca el hueco
 * `surname_split_unconfirmed`.
 *
 * Vive dentro de `<Form>` de `ImdertyProfileForm` — recibe su `control`
 * (misma forma que `ImdertyProfileUpdateValues`) en vez de gestionar su
 * propio `useForm`, para que los tres campos viajen en el mismo PUT.
 */
import { CheckCircle2, TriangleAlert } from "lucide-react";
import type { Control } from "react-hook-form";

import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import type { ProfileFormInputValues } from "@/components/imderty/ImdertyProfileForm";

export interface SurnameSplitConfirmProps {
  control: Control<ProfileFormInputValues>;
  proposedFirst: string | null;
  proposedSecond: string | null;
  /** Estado confirmado según la última respuesta del servidor (no el checkbox en vivo). */
  alreadyConfirmed: boolean;
}

export function SurnameSplitConfirm({
  control,
  proposedFirst,
  proposedSecond,
  alreadyConfirmed,
}: SurnameSplitConfirmProps) {
  return (
    <div className="space-y-3 rounded-lg border border-hairline p-3">
      <div className="flex items-center gap-2">
        {alreadyConfirmed ? (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
        ) : (
          <TriangleAlert className="h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
        )}
        <p className="text-sm font-medium text-charcoal">
          {alreadyConfirmed
            ? "División de apellidos confirmada"
            : "Confirma la división de apellidos"}
        </p>
      </div>

      {!alreadyConfirmed && (proposedFirst || proposedSecond) && (
        <p className="text-xs text-mid-gray">
          Propuesta automática: <span className="font-medium">{proposedFirst ?? "—"}</span>
          {" · "}
          <span className="font-medium">{proposedSecond ?? "—"}</span>. Corrígela si hace
          falta antes de confirmar.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <FormField
          control={control}
          name="first_surname"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Primer apellido</FormLabel>
              <FormControl>
                <Input {...field} value={field.value ?? ""} autoComplete="off" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="second_surname"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Segundo apellido</FormLabel>
              <FormControl>
                <Input {...field} value={field.value ?? ""} autoComplete="off" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <FormField
        control={control}
        name="confirm_surname_split"
        render={({ field }) => (
          <FormItem className="flex flex-row items-start gap-2 space-y-0">
            <FormControl>
              <Checkbox
                checked={Boolean(field.value)}
                onCheckedChange={(checked) => field.onChange(checked === true)}
              />
            </FormControl>
            <div className="space-y-0.5 leading-none">
              <FormLabel className="text-sm font-normal">
                Confirmo que el primer y segundo apellido son correctos
              </FormLabel>
              <FormMessage />
            </div>
          </FormItem>
        )}
      />
    </div>
  );
}
