/**
 * StaffCreateSheet — hoja "Nuevo entrenador" (feature 041 — gobernanza
 * multi-coach, US3). contracts/staff-admin.md §9.
 *
 * RHF + Zod (`staffCreateSchema`) sobre `ui/sheet.tsx`; Radix aporta el
 * focus trap, Escape y scroll lock (R-29 — no se reimplementa el `role`
 * a mano como `ParentFormDialog`). `role` va fijo a `"coach"` porque un
 * admin solo puede crear entrenadores (`_ALLOWED_CREATIONS`), pero el
 * schema sigue declarando `role` porque la regla del club obligatorio es
 * una propiedad del rol creado.
 */
import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useClubs } from "@/hooks/admin/useClubs";
import { useCreateStaff } from "@/hooks/admin/useCreateStaff";
import { extractErrorDetail } from "@/lib/apiError";
import { staffCreateSchema } from "@/schemas/staff.schema";
import { UserRole } from "@/types/enums";
import type { z } from "zod";

type StaffCreateFormValues = z.input<typeof staffCreateSchema>;

export interface StaffCreateSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

const inputWrapperClass = "space-y-1";
const labelClass = "text-xs font-medium text-mid-gray";

export function StaffCreateSheet({
  open,
  onOpenChange,
  onCreated,
}: StaffCreateSheetProps) {
  const clubsQuery = useClubs();
  const createMutation = useCreateStaff();
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const form = useForm<StaffCreateFormValues>({
    resolver: zodResolver(staffCreateSchema),
    defaultValues: {
      first_name: "",
      last_name: "",
      email: "",
      phone: "",
      role: "coach",
      club_id: null,
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({
        first_name: "",
        last_name: "",
        email: "",
        phone: "",
        role: "coach",
        club_id: null,
      });
      setSubmitError(null);
      createMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function handleSubmit(values: StaffCreateFormValues) {
    setSubmitError(null);
    createMutation.mutate(
      {
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        phone: values.phone || null,
        role: UserRole.coach,
        club_id: values.club_id as number,
      },
      {
        onSuccess: () => {
          onCreated?.();
          onOpenChange(false);
        },
        onError: (err) => {
          const detail = extractErrorDetail(
            err,
            "No se pudo crear la cuenta. Intenta de nuevo.",
          );
          const status = (err as { response?: { status?: number } })?.response
            ?.status;
          if (status === 422) {
            form.setError("club_id", { message: detail });
          } else if (status === 409) {
            form.setError("email", {
              message: "Ya existe un usuario con ese correo electrónico",
            });
          } else {
            setSubmitError(detail);
          }
        },
      },
    );
  }

  const isPending = createMutation.isPending;

  return (
    <Sheet open={open} onOpenChange={(next) => !isPending && onOpenChange(next)}>
      <SheetContent data-testid="staff-create-sheet" side="right">
        <form
          className="flex h-full flex-col"
          onSubmit={form.handleSubmit(handleSubmit)}
          noValidate
        >
          <SheetHeader>
            <SheetTitle>Nuevo entrenador</SheetTitle>
            <SheetDescription>
              La persona recibirá un correo para definir su contraseña.
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="space-y-4">
            <div className={inputWrapperClass}>
              <label htmlFor="staff-first-name" className={labelClass}>
                Nombres
              </label>
              <Input
                id="staff-first-name"
                autoComplete="off"
                aria-invalid={!!form.formState.errors.first_name}
                {...form.register("first_name")}
              />
              {form.formState.errors.first_name && (
                <p role="alert" className="text-sm text-danger">
                  {form.formState.errors.first_name.message}
                </p>
              )}
            </div>

            <div className={inputWrapperClass}>
              <label htmlFor="staff-last-name" className={labelClass}>
                Apellidos
              </label>
              <Input
                id="staff-last-name"
                autoComplete="off"
                aria-invalid={!!form.formState.errors.last_name}
                {...form.register("last_name")}
              />
              {form.formState.errors.last_name && (
                <p role="alert" className="text-sm text-danger">
                  {form.formState.errors.last_name.message}
                </p>
              )}
            </div>

            <div className={inputWrapperClass}>
              <label htmlFor="staff-email" className={labelClass}>
                Correo electrónico
              </label>
              <Input
                id="staff-email"
                type="email"
                autoComplete="off"
                aria-invalid={!!form.formState.errors.email}
                {...form.register("email")}
              />
              {form.formState.errors.email && (
                <p role="alert" className="text-sm text-danger">
                  {form.formState.errors.email.message}
                </p>
              )}
            </div>

            <div className={inputWrapperClass}>
              <label htmlFor="staff-phone" className={labelClass}>
                Teléfono (opcional)
              </label>
              <Input id="staff-phone" type="tel" {...form.register("phone")} />
            </div>

            <div className={inputWrapperClass}>
              <label htmlFor="staff-club-select" className={labelClass}>
                Club
              </label>
              <Controller
                control={form.control}
                name="club_id"
                render={({ field }) => (
                  <Select
                    value={field.value ? String(field.value) : ""}
                    onValueChange={(value) => field.onChange(Number(value))}
                  >
                    <SelectTrigger
                      id="staff-club-select"
                      data-testid="staff-club-select"
                      aria-invalid={!!form.formState.errors.club_id}
                    >
                      <SelectValue placeholder="Selecciona un club" />
                    </SelectTrigger>
                    <SelectContent>
                      {(clubsQuery.data ?? []).map((club) => (
                        <SelectItem key={club.id} value={String(club.id)}>
                          {club.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {form.formState.errors.club_id && (
                <p role="alert" className="text-sm text-danger">
                  {form.formState.errors.club_id.message}
                </p>
              )}
            </div>

            {submitError && (
              <p role="alert" className="text-sm text-danger">
                {submitError}
              </p>
            )}
          </SheetBody>

          <SheetFooter>
            <Button
              type="button"
              variant="outline"
              className="min-h-12"
              disabled={isPending}
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              className="min-h-12"
              disabled={isPending}
              data-testid="staff-create-submit"
            >
              {isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Crear entrenador
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
