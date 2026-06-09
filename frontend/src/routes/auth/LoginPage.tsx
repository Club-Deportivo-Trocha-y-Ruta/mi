import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, Navigate, useNavigate } from "react-router-dom";
import axios from "axios";
import { z } from "zod";

import { useAuthStore } from "@/store/auth.store";
import { landingPathForRole } from "@/lib/landing";

const loginSchema = z.object({
  email: z.string().email("Ingresa un correo válido"),
  password: z.string().min(6, "La contraseña debe tener mínimo 6 caracteres"),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isLoading = useAuthStore((state) => state.isLoading);
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  // Si ya hay una sesión válida, nunca mostrar el formulario de login:
  // la primera vista debe ser el panel del usuario (Dashboard / Mis atletas).
  //
  // IMPORTANTE: este return va DESPUÉS de todos los hooks (useForm incluido).
  // Cuando login() actualiza el store, este componente re-renderiza con
  // isAuthenticated=true; si el return estuviera antes de useForm, React
  // contaría menos hooks que en el render previo ("Rendered fewer hooks than
  // expected") y el árbol se rompería durante la transición SPA → pantalla en
  // blanco en la primera navegación post-login.
  if (isAuthenticated && user) {
    return <Navigate to={landingPathForRole(user.role)} replace />;
  }

  const onSubmit = async (values: LoginForm) => {
    setServerError(null);
    try {
      await login(values.email, values.password);
      const role = useAuthStore.getState().user?.role ?? user?.role;
      navigate(landingPathForRole(role), { replace: true });
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
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
      >
        {/* Header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-mid-gray">
            Club Deportivo
          </p>
          <h1
            className="mt-1 text-2xl text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
              letterSpacing: "0.2px",
            }}
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
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <p className="mt-1 text-xs text-red-600">
                {form.formState.errors.password.message}
              </p>
            )}
            <div className="mt-1.5 text-right">
              <Link
                to="/recuperar-contrasena"
                className="text-xs font-medium text-link-blue hover:underline"
              >
                ¿Olvidaste tu contraseña?
              </Link>
            </div>
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
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {isLoading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>
      </div>
    </div>
  );
}
