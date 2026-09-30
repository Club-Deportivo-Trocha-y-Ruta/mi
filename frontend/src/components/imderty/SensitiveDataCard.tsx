/**
 * SensitiveDataCard — bloque de etnia, discapacidad y víctima del conflicto
 * armado del perfil IMDERTY (feature 047).
 *
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md` §Sensitive
 * data. El bloque completo depende de una autorización activa del
 * acudiente — sin ella el backend nunca entrega ni acepta valores
 * (`GET .../sensitive-data` → 404, `PUT .../sensitive-data` → 403), así que
 * la tarjeta se bloquea del mismo modo: nada de los tres campos se lee ni
 * se edita hasta registrar la autorización.
 *
 * - **Registrar**: diálogo (no `window.confirm`) con acudiente + fecha.
 * - **Editar**: los tres selects de listas oficiales, valores por defecto
 *   «NO SABE NO RESPONDE» / «N/A»; víctima del conflicto no tiene default,
 *   se exige elegir explícitamente antes de guardar (data-model.md).
 * - **Retirar**: diálogo de confirmación — borra la fila de datos sensibles.
 *
 * No hay, y nunca debe haber, un campo de orientación sexual (FR-009).
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Lock, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

import { cn } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCreateSensitiveAuthorization,
  useSensitiveData,
  useUpdateSensitiveData,
  useWithdrawSensitiveAuthorization,
} from "@/hooks/useImderty";
import {
  imdertyDisabilities,
  imdertyDisabilitySchema,
  imdertyDisabilityLabels,
  imdertyEthnicities,
  imdertyEthnicitySchema,
  imdertyEthnicityLabels,
  imdertyYesNoLabels,
  imdertyYesNoSchema,
  sensitiveAuthorizationCreateSchema,
  type ImdertyGuardian,
  type SensitiveAuthorization,
  type SensitiveAuthorizationCreateValues,
  type SensitiveData,
} from "@/schemas/imderty";

export interface SensitiveDataCardProps {
  athleteId: number;
  guardians: ImdertyGuardian[];
  authorization: SensitiveAuthorization | null;
}

/** Extrae un mensaje de error legible para las mutaciones de este bloque. */
function getSensitiveErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null) {
    const e = err as { response?: { data?: { detail?: unknown }; status?: number } };
    const status = e.response?.status;
    if (status === 409) return "Ya existe una autorización activa para este atleta.";
    if (status === 404) return "No hay una autorización activa registrada.";
    if (status === 403) return "Sin permiso para realizar esta acción.";
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export function SensitiveDataCard({ athleteId, guardians, authorization }: SensitiveDataCardProps) {
  const isActive = Boolean(authorization?.active);
  const [recordOpen, setRecordOpen] = React.useState(false);
  const [withdrawOpen, setWithdrawOpen] = React.useState(false);

  const withdraw = useWithdrawSensitiveAuthorization(athleteId);

  function handleWithdraw() {
    withdraw.mutate(undefined, {
      onSuccess: () => {
        toast.success("Autorización retirada. Los datos sensibles fueron borrados.");
        setWithdrawOpen(false);
      },
      onError: (err) => {
        toast.error(getSensitiveErrorMessage(err, "No fue posible retirar la autorización. Intenta de nuevo."));
      },
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-base">Datos sensibles IMDERTY</CardTitle>
        {isActive && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Autorizado
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {!isActive ? (
          <LockedState onRecord={() => setRecordOpen(true)} guardianCount={guardians.length} />
        ) : (
          <>
            <SensitiveDataEditor athleteId={athleteId} />
            <div className="border-t border-hairline pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setWithdrawOpen(true)}
                className="w-full sm:w-auto"
              >
                Retirar autorización
              </Button>
            </div>
          </>
        )}
      </CardContent>

      <RecordAuthorizationDialog
        open={recordOpen}
        onOpenChange={setRecordOpen}
        athleteId={athleteId}
        guardians={guardians}
      />

      <ConfirmDialog
        open={withdrawOpen}
        title="Retirar autorización"
        description="Al retirar la autorización, la etnia, discapacidad y condición de víctima del conflicto armado registradas para este atleta se borrarán de inmediato. Podrás registrar una nueva autorización más adelante."
        confirmLabel="Retirar autorización"
        tone="danger"
        isPending={withdraw.isPending}
        errorMessage={
          withdraw.isError
            ? getSensitiveErrorMessage(withdraw.error, "No fue posible retirar la autorización. Intenta de nuevo.")
            : undefined
        }
        onConfirm={handleWithdraw}
        onCancel={() => setWithdrawOpen(false)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Estado bloqueado
// ---------------------------------------------------------------------------

function LockedState({ onRecord, guardianCount }: { onRecord: () => void; guardianCount: number }) {
  return (
    <Alert>
      <Lock aria-hidden="true" />
      {/*
        Sin `AlertTitle` (h5) a propósito, igual que `ReadinessPanel`: la
        tarjeta ya abre con el `CardTitle` (h3), y un h5 directo debajo salta
        el h4 (regla axe heading-order). El texto en negrita cumple el mismo
        rol visual sin semántica de encabezado.
      */}
      <p className="mb-1 font-medium leading-none tracking-tight">
        <strong>Bloqueado sin autorización</strong>
      </p>
      <AlertDescription className="space-y-3">
        <p>
          La etnia, la discapacidad y la condición de víctima del conflicto armado son datos
          sensibles: solo se registran y se muestran cuando un acudiente autoriza explícitamente
          su captura para la planilla IMDERTY.
        </p>
        <Button
          type="button"
          onClick={onRecord}
          disabled={guardianCount === 0}
          className="w-full sm:w-auto"
        >
          Registrar autorización
        </Button>
        {guardianCount === 0 && (
          <p className="text-xs text-mid-gray">
            Este atleta no tiene un acudiente vinculado todavía; no se puede registrar la
            autorización hasta que exista uno.
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}

// ---------------------------------------------------------------------------
// Diálogo: registrar autorización
// ---------------------------------------------------------------------------

const recordFormSchema = sensitiveAuthorizationCreateSchema;
type RecordFormValues = SensitiveAuthorizationCreateValues;

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

interface RecordAuthorizationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  athleteId: number;
  guardians: ImdertyGuardian[];
}

function RecordAuthorizationDialog({
  open,
  onOpenChange,
  athleteId,
  guardians,
}: RecordAuthorizationDialogProps) {
  const createAuthorization = useCreateSensitiveAuthorization(athleteId);

  const form = useForm<RecordFormValues>({
    resolver: zodResolver(recordFormSchema),
    defaultValues: { guardian_user_id: 0, authorized_on: todayIsoDate() },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({ guardian_user_id: guardians[0]?.user_id ?? 0, authorized_on: todayIsoDate() });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function onSubmit(values: RecordFormValues) {
    createAuthorization.mutate(values, {
      onSuccess: () => {
        toast.success("Autorización registrada.");
        onOpenChange(false);
      },
      onError: (err) => {
        toast.error(
          getSensitiveErrorMessage(err, "No fue posible registrar la autorización. Intenta de nuevo."),
        );
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] w-[calc(100%-2rem)] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Registrar autorización</DialogTitle>
          <DialogDescription>
            Selecciona el acudiente que autoriza y la fecha en la que dio su consentimiento.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogBody className="space-y-4">
              <FormField
                control={form.control}
                name="guardian_user_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Acudiente</FormLabel>
                    <Select
                      value={field.value ? String(field.value) : undefined}
                      onValueChange={(value) => field.onChange(Number(value))}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Selecciona un acudiente" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {guardians.map((guardian) => (
                          <SelectItem key={guardian.user_id} value={String(guardian.user_id)}>
                            {guardian.display_name}
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
                name="authorized_on"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Fecha de autorización</FormLabel>
                    <FormControl>
                      <Input type="date" max={todayIsoDate()} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </DialogBody>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={createAuthorization.isPending}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={createAuthorization.isPending}>
                {createAuthorization.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                )}
                Registrar
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Edición de los tres campos
// ---------------------------------------------------------------------------

/**
 * `conflict_victim` no tiene default (data-model.md): a diferencia del
 * schema del contrato (que acepta `null`), este formulario exige elegir
 * SI/NO explícitamente antes de habilitar el guardado.
 */
const editFormSchema = z
  .object({
    ethnicity: imdertyEthnicitySchema,
    disability: imdertyDisabilitySchema,
    conflict_victim: imdertyYesNoSchema.optional(),
  })
  .refine((data) => data.conflict_victim !== undefined, {
    message: "Selecciona SI o NO",
    path: ["conflict_victim"],
  });
type EditFormValues = z.infer<typeof editFormSchema>;

function editDefaultsFrom(data: SensitiveData | undefined): EditFormValues {
  return {
    ethnicity: data?.ethnicity ?? "NO SABE NO RESPONDE",
    disability: data?.disability ?? "N/A",
    conflict_victim: data?.conflict_victim ?? undefined,
  };
}

function SensitiveDataEditor({ athleteId }: { athleteId: number }) {
  const { data, isLoading, isError } = useSensitiveData(athleteId, true);
  const updateSensitiveData = useUpdateSensitiveData(athleteId);

  const form = useForm<EditFormValues>({
    resolver: zodResolver(editFormSchema),
    values: data ? editDefaultsFrom(data) : undefined,
    defaultValues: editDefaultsFrom(undefined),
  });

  function onSubmit(values: EditFormValues) {
    // El refine de arriba garantiza `conflict_victim` definido en este punto.
    updateSensitiveData.mutate(
      { ...values, conflict_victim: values.conflict_victim as "si" | "no" },
      {
        onSuccess: () => {
          toast.success("Datos sensibles actualizados.");
        },
        onError: (err) => {
          toast.error(getSensitiveErrorMessage(err, "No fue posible guardar los cambios. Intenta de nuevo."));
        },
      },
    );
  }

  if (isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Cargando datos sensibles…" className="space-y-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <Alert variant="destructive">
        {/* Sin `AlertTitle` (h5): mismo motivo que `LockedState` (heading-order). */}
        <AlertDescription>
          <strong>No se pudieron cargar los datos sensibles</strong>. Recarga la página o intenta
          de nuevo en un momento.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="ethnicity"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Etnia</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona una opción" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {imdertyEthnicities.map((value) => (
                      <SelectItem key={value} value={value}>
                        {imdertyEthnicityLabels[value]}
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
            name="disability"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Discapacidad</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona una opción" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {imdertyDisabilities.map((value) => (
                      <SelectItem key={value} value={value}>
                        {imdertyDisabilityLabels[value]}
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
            name="conflict_victim"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Víctima del conflicto armado</FormLabel>
                <Select value={field.value ?? undefined} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className={cn(!field.value && "text-mid-gray")}>
                      <SelectValue placeholder="Selecciona SI o NO" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="si">{imdertyYesNoLabels.si}</SelectItem>
                    <SelectItem value="no">{imdertyYesNoLabels.no}</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <Button type="submit" disabled={updateSensitiveData.isPending} className="w-full sm:w-auto">
          {updateSensitiveData.isPending && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          Guardar datos sensibles
        </Button>
      </form>
    </Form>
  );
}
