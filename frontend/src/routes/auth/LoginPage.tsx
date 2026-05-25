import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { z } from "zod";

import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

const loginSchema = z.object({
  email: z.string().email("Ingresa un correo válido"),
  password: z.string().min(6, "La contraseña debe tener mínimo 6 caracteres"),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const user = useAuthStore((state) => state.user);
  const isLoading = useAuthStore((state) => state.isLoading);
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const onSubmit = async (values: LoginForm) => {
    setServerError(null);
    try {
      await login(values.email, values.password);
      const role = useAuthStore.getState().user?.role ?? user?.role;
      if (role === UserRole.admin || role === UserRole.coach) {
        navigate("/dashboard", { replace: true });
      } else if (role === UserRole.parent) {
        navigate("/my-athletes", { replace: true });
      } else {
        navigate("/", { replace: true });
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        setServerError("Credenciales inválidas. Verifica tu correo y contraseña.");
      } else {
        setServerError("No fue posible iniciar sesión. Intenta de nuevo.");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      {/* Login card — shadow Level 2 (ring + soft), 12px radius */}
      <div
        className="w-full max-w-md rounded-xl bg-white p-8"
      >
        {/* Header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Club Deportivo
          </p>
          <h1
            className="mt-1 text-2xl text-charcoal font-heading tracking-[0.2px]"
          >
            Trocha y Ruta
          </h1>
        </div>

        <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
          {/* Email field */}
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
              className="w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50"
              {...form.register("email")}
            />
            {form.formState.errors.email && (
              <p className="mt-1 text-xs text-red-600">
                {form.formState.errors.email.message}
              </p>
            )}
          </div>

          {/* Password field */}
          <div>
            <label
              htmlFor="password"
              className="mb-1.5 block text-sm font-medium text-charcoal"
            >
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              className="w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50"
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <p className="mt-1 text-xs text-red-600">
                {form.formState.errors.password.message}
              </p>
            )}
          </div>

          {serverError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {serverError}
            </p>
          )}

          {/* Primary CTA button — charcoal bg, white text, 8px radius */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50"
          >
            {isLoading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>
      </div>
    </div>
  );
}
