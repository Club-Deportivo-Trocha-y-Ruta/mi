import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import { z } from "zod";

import { requestPasswordReset } from "@/api/auth";

const forgotSchema = z.object({
  email: z.string().email("Ingresa un correo válido"),
});

type ForgotForm = z.infer<typeof forgotSchema>;

// Mensaje neutral idéntico al del backend: nunca revela si la cuenta existe.
const NEUTRAL_MESSAGE =
  "Si el correo está registrado, te enviamos un enlace para restablecer tu contraseña. Revisa tu bandeja de entrada y la carpeta de spam.";

export function ForgotPasswordPage() {
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<ForgotForm>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = async (values: ForgotForm) => {
    setServerError(null);
    try {
      await requestPasswordReset({ email: values.email });
      setSubmitted(true);
    } catch {
      // No exponemos detalle: error genérico y reintento posible.
      setServerError(
        "No fue posible procesar tu solicitud. Intenta de nuevo en unos minutos.",
      );
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="w-full max-w-md rounded-xl bg-white p-8"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
      >
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Recuperar acceso
          </p>
          <h1
            className="mt-1 text-2xl text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
              letterSpacing: "0.2px",
            }}
          >
            ¿Olvidaste tu contraseña?
          </h1>
        </div>

        {submitted ? (
          <div>
            <p
              className="rounded-lg bg-green-50 px-3 py-3 text-sm text-green-800"
              role="status"
            >
              {NEUTRAL_MESSAGE}
            </p>
            <div className="mt-6 text-center">
              <Link
                to="/login"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Volver a iniciar sesión
              </Link>
            </div>
          </div>
        ) : (
          <form
            className="space-y-5"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <p className="text-sm text-mid-gray">
              Ingresa el correo de tu cuenta y te enviaremos un enlace para crear
              una nueva contraseña.
            </p>

            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-charcoal"
              >
                Correo
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                className="w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                {...form.register("email")}
              />
              {form.formState.errors.email && (
                <p className="mt-1 text-xs text-red-600">
                  {form.formState.errors.email.message}
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
              className="w-full rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50"
              style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
            >
              {form.formState.isSubmitting
                ? "Enviando..."
                : "Enviar enlace"}
            </button>

            <div className="text-center">
              <Link
                to="/login"
                className="text-sm font-medium text-link-blue hover:underline"
              >
                Volver a iniciar sesión
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
