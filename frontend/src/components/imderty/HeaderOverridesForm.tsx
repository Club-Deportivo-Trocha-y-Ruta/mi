/**
 * HeaderOverridesForm — encabezado de la planilla IMDERTY, editable solo
 * para esta descarga (feature 047, US3, T044).
 *
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md` §Club
 * IMDERTY settings / §Sheet. Los valores se precargan desde
 * `GET /api/clubs/{club_id}/imderty-settings` (`useClubImdertySettings`).
 * Este componente NO tiene botón "Guardar" propio ni llama a
 * `useUpdateClubImdertySettings`: el contrato persiste el encabezado como
 * configuración del club dentro del MISMO `POST .../imderty-sheet` cuando
 * `save_header_as_default=true` — por eso solo emite los valores actuales
 * hacia el padre (`ImdertySheetPage`), que los adjunta al pedido de
 * descarga. Sin marcar la casilla, la configuración guardada del club queda
 * intacta (US3, acceptance scenario 2).
 */
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Form, FormControl, FormField, FormItem, FormLabel } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useClubImdertySettings } from "@/hooks/useImderty";
import {
  imdertyPrograms,
  imdertyProgramLabels,
  imdertySheetHeaderSchema,
  type ImdertyProgram,
  type ImdertySheetHeaderValues,
} from "@/schemas/imderty";

export interface HeaderOverridesFormProps {
  clubId: number;
  saveAsDefault: boolean;
  onSaveAsDefaultChange: (value: boolean) => void;
  /**
   * Se llama con los valores actuales del formulario — pero solo una vez
   * que `useClubImdertySettings` termina de resolver (éxito o error), nunca
   * mientras `isLoading`. Si el padre mandara los defaults en blanco de
   * este formulario ANTES de que la configuración guardada cargara, una
   * descarga disparada en esa ventana perdería el encabezado del club en
   * vez de heredarlo (contrato §Sheet: `header` ausente ⇒ se usa la
   * configuración guardada — un objeto en blanco explícito YA NO cuenta
   * como ausente).
   */
  onChange: (header: ImdertySheetHeaderValues) => void;
}

const BLANK_HEADER: ImdertySheetHeaderValues = {
  contractor_name: null,
  venue: null,
  training_days: null,
  schedule: null,
  programs: [],
};

function HeaderSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando configuración del encabezado…"
      className="space-y-3"
    >
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export function HeaderOverridesForm({
  clubId,
  saveAsDefault,
  onSaveAsDefaultChange,
  onChange,
}: HeaderOverridesFormProps) {
  const { data: settings, isLoading, isError } = useClubImdertySettings(clubId);

  const form = useForm<ImdertySheetHeaderValues>({
    resolver: zodResolver(imdertySheetHeaderSchema),
    values: settings
      ? {
          contractor_name: settings.contractor_name,
          venue: settings.venue,
          training_days: settings.training_days,
          schedule: settings.schedule,
          programs: settings.programs,
        }
      : undefined,
    defaultValues: BLANK_HEADER,
  });

  const watched = useWatch({ control: form.control });
  const programs = (watched.programs ?? []) as ImdertyProgram[];

  useEffect(() => {
    // Mientras `isLoading`, todavía no se sabe si el club tiene
    // configuración guardada: no emitir el formulario en blanco (ver el
    // comentario de `onChange` en las props).
    if (isLoading) return;
    onChange({
      contractor_name: watched.contractor_name ?? null,
      venue: watched.venue ?? null,
      training_days: watched.training_days ?? null,
      schedule: watched.schedule ?? null,
      programs,
    });
    // Solo se debe re-emitir cuando cambian los valores del formulario, no
    // cuando el padre re-renderiza con una nueva identidad de `onChange`
    // (mismo patrón que `SensitiveDataCard`'s reset effect).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(watched), isLoading]);

  function toggleProgram(program: ImdertyProgram, checked: boolean) {
    const next = checked ? [...programs, program] : programs.filter((p) => p !== program);
    form.setValue("programs", next, { shouldDirty: true });
  }

  if (isLoading) {
    return <HeaderSkeleton />;
  }

  return (
    <div className="space-y-5">
      {isError && (
        <Alert variant="warning">
          <AlertDescription>
            No se pudo cargar la configuración guardada del club. Puedes escribir los valores
            para esta descarga de todas formas.
          </AlertDescription>
        </Alert>
      )}

      <Form {...form}>
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="contractor_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Contratista</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value || null)}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="venue"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Sede de entrenamiento</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value || null)}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="training_days"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Días de entrenamiento</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Ej. LUNES A VIERNES"
                      {...field}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value || null)}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="schedule"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Horario</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Ej. 4:00 PM A 6:00 PM"
                      {...field}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value || null)}
                    />
                  </FormControl>
                </FormItem>
              )}
            />
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-charcoal">Programa IMDERTY</legend>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {imdertyPrograms.map((program) => {
                const checked = programs.includes(program);
                const inputId = `imderty-header-program-${program}`;
                return (
                  <div key={program} className="flex items-center gap-2">
                    <Checkbox
                      id={inputId}
                      checked={checked}
                      onCheckedChange={(value) => toggleProgram(program, value === true)}
                    />
                    <Label htmlFor={inputId} className="text-sm font-normal">
                      {imdertyProgramLabels[program]}
                    </Label>
                  </div>
                );
              })}
            </div>
          </fieldset>

          <div className="flex items-center gap-2 border-t border-hairline pt-4">
            <Checkbox
              id="imderty-header-save-default"
              checked={saveAsDefault}
              onCheckedChange={(value) => onSaveAsDefaultChange(value === true)}
            />
            <Label htmlFor="imderty-header-save-default" className="text-sm font-normal">
              Guardar como predeterminado
            </Label>
          </div>
        </div>
      </Form>
    </div>
  );
}

export default HeaderOverridesForm;
