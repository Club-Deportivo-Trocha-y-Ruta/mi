import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { confirmPasswordReset, validateResetToken } from "@/api/auth";

const resetSchema = z
  .object({
    password: z.string().min(8, "La contraseña debe tener al menos 8 caracteres"),
    confirm: z.string(),
  })
  .refine((data) => data.password === data.confirm, {
    message: "Las contraseñas no coinciden",
    path: ["confirm"],
  });

type ResetForm = z.infer<typeof resetSchema>;

type Status = "checking" | "valid" | "invalid" | "done";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<Status>("checking");
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<ResetForm>({
    resolver: zodResolver(resetSchema),
    defaultValues: { password: "", confirm: "" },
  });

  useEffect(() => {
    let active = true;
    if (!token) {
      setStatus("invalid");
      return;
    }
    validateResetToken(token)
      .then(() => {
        if (active) setStatus("valid");
      })
      .catch(() => {
        // 404/410 → enlace no válido o expirado (mismo tratamiento).
        if (active) setStatus("invalid");
      });
    return () => {
      active = false;
    };
  }, [token]);

  const onSubmit = async (values: ResetForm) => {
    setServerError(null);
    try {
      await confirmPasswordReset({ token, new_password: values.password });
      setStatus("done");
    } catch (error: unknown) {
      const httpStatus =
        typeof error === "object" && error !== null && "response" in error
          ? (error as { response?: { status?: number } }).response?.status
          : undefined;
      if (httpStatus === 404 || httpStatus === 410) {
        setStatus("invalid");
      } else {
        setServerError(
          "No fue posible actualizar tu contraseña. Intenta de nuevo.",
        );
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-card">
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Recuperar acceso
          </p>
          <h1
            className="font-display mt-1 text-2xl text-charcoal"
            style={{ letterSpacing: "0.2px" }}
          >
            Crear nueva contraseña
          </h1>
        </div>

        {status === "checking" && (
          <p className="text-center text-sm text-mid-gray" role="status">
            Validando el enlace...
          </p>
        )}

        {status === "invalid" && (
          <div>
            <p
              className="rounded-lg bg-amber-50 px-3 py-3 text-sm text-amber-800"
              role="alert"
            >
              El enlace ha expirado o ya fue utilizado. Solicita uno nuevo para
              continuar.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/recuperar-contrasena"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Solicitar un nuevo enlace
              </Link>
            </div>
          </div>
        )}

        {status === "done" && (
          <div>
            <p
              className="rounded-lg bg-green-50 px-3 py-3 text-sm text-green-800"
              role="status"
            >
              Tu contraseña fue actualizada. Ya puedes iniciar sesión.
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/login"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Ir a iniciar sesión
              </Link>
            </div>
          </div>
        )}

        {status === "valid" && (
          <form
            className="space-y-5"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-charcoal"
              >
                Nueva contraseña
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                className="w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring"
                {...form.register("password")}
              />
              {form.formState.errors.password && (
                <p className="mt-1 text-xs text-red-600">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="confirm"
                className="mb-1.5 block text-sm font-medium text-charcoal"
              >
                Confirmar contraseña
              </label>
              <input
                id="confirm"
                type="password"
                autoComplete="new-password"
                className="w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring"
                {...form.register("confirm")}
              />
              {form.formState.errors.confirm && (
                <p className="mt-1 text-xs text-red-600">
                  {form.formState.errors.confirm.message}
                </p>
              )}
            </div>

            {serverError && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {serverError}
              </p>
            )}

            <button
              type="submit"
              disabled={form.formState.isSubmitting}
              className="w-full rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 shadow-button-highlight"
            >
              {form.formState.isSubmitting
                ? "Actualizando..."
                : "Actualizar contraseña"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
