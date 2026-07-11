import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useCreateParentUser } from "@/hooks/parents/useCreateParentUser";

const parentFormSchema = z.object({
  first_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
  last_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
});

type ParentFormValues = z.infer<typeof parentFormSchema>;

interface ParentFormDialogProps {
  clubId: number;
  open: boolean;
  onClose: () => void;
}

const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 disabled:bg-light-gray disabled:text-mid-gray shadow-ring";

export function ParentFormDialog({ clubId, open, onClose }: ParentFormDialogProps) {
  const createMutation = useCreateParentUser();

  const form = useForm<ParentFormValues>({
    resolver: zodResolver(parentFormSchema),
    defaultValues: {
      first_name: "",
      last_name: "",
    },
  });

  // Reset form each time dialog opens
  useEffect(() => {
    if (open) {
      form.reset();
      createMutation.reset();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  function handleSubmit(values: ParentFormValues) {
    createMutation.mutate(
      {
        first_name: values.first_name,
        last_name: values.last_name,
        email: null,
        phone: null,
        password: null,
        club_id: clubId,
      },
      {
        onSuccess: () => {
          onClose();
        },
      },
    );
  }

  const submitError =
    createMutation.isError
      ? (createMutation.error as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail ?? "No se pudo crear el padre/acudiente."
      : null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="parent-dialog-title"
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div
          className="w-full max-w-md overflow-y-auto rounded-xl bg-white p-6 shadow-card"
          style={{ maxHeight: "90dvh" }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="mb-5 flex items-center justify-between">
            <h2
              id="parent-dialog-title"
              className="font-display text-base text-charcoal"
            >
              Nuevo padre / acudiente
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-2 py-1 text-sm text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal"
              aria-label="Cerrar"
            >
              ✕
            </button>
          </div>

          {/* Form */}
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium text-charcoal">
                Nombres
                <input
                  className={inputClass}
                  placeholder="Juan"
                  autoComplete="off"
                  {...form.register("first_name")}
                />
                <span className="text-xs text-red-600">
                  {form.formState.errors.first_name?.message}
                </span>
              </label>

              <label className="text-sm font-medium text-charcoal">
                Apellidos
                <input
                  className={inputClass}
                  placeholder="Garcia"
                  autoComplete="off"
                  {...form.register("last_name")}
                />
                <span className="text-xs text-red-600">
                  {form.formState.errors.last_name?.message}
                </span>
              </label>
            </div>

            <p className="rounded-lg bg-light-gray px-3 py-2 text-xs text-mid-gray">
              El padre/acudiente recibirá una invitación por email para completar
              sus datos de acceso (correo, teléfono y contraseña).
            </p>

            {submitError && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {submitError}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm font-medium text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 shadow-button-highlight"
              >
                {createMutation.isPending ? "Guardando..." : "Crear padre"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
