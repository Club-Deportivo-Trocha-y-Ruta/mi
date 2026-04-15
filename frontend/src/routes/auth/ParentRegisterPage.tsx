import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useSearchParams } from "react-router-dom";
import axios from "axios";
import { z } from "zod";

import { validateInviteToken, registerParent } from "@/api/auth";
import type { ParentInviteTokenValidation } from "@/types/parent.types";

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const schema = z.object({
  first_name: z.string().min(1, "El nombre es requerido"),
  last_name: z.string().min(1, "El apellido es requerido"),
  password: z.string().min(8, "La contraseña debe tener mínimo 8 caracteres"),
  phone: z.string().optional(),
});

type RegisterForm = z.infer<typeof schema>;

// ---------------------------------------------------------------------------
// Shared style constants (mirror LoginPage)
// ---------------------------------------------------------------------------

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const INPUT_SHADOW = "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px";

const inputClassName =
  "w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50";

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

type PageState = "loading" | "invalid" | "form" | "success";

export function ParentRegisterPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [pageState, setPageState] = useState<PageState>("loading");
  const [tokenData, setTokenData] = useState<ParentInviteTokenValidation | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [successName, setSuccessName] = useState<string>("");

  const form = useForm<RegisterForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      first_name: "",
      last_name: "",
      password: "",
      phone: "",
    },
  });

  // -------------------------------------------------------------------------
  // Validate token on mount
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (!token) {
      setPageState("invalid");
      return;
    }

    let cancelled = false;

    validateInviteToken(token)
      .then((data) => {
        if (cancelled) return;
        if (data.valid) {
          setTokenData(data);
          setPageState("form");
        } else {
          setPageState("invalid");
        }
      })
      .catch(() => {
        if (!cancelled) setPageState("invalid");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  // -------------------------------------------------------------------------
  // Submit
  // -------------------------------------------------------------------------

  const onSubmit = async (values: RegisterForm) => {
    setServerError(null);
    try {
      const result = await registerParent({
        token,
        first_name: values.first_name,
        last_name: values.last_name,
        password: values.password,
        phone: values.phone || null,
      });
      setSuccessName(tokenData?.athlete_name ?? result.first_name);
      setPageState("success");
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const status = error.response?.status;
        if (status === 410) {
          setServerError("La invitación expiró o ya fue usada.");
        } else if (status === 409) {
          setServerError("Ya existe una cuenta con este correo.");
        } else {
          setServerError("No fue posible crear la cuenta. Intenta de nuevo.");
        }
      } else {
        setServerError("No fue posible crear la cuenta. Intenta de nuevo.");
      }
    }
  };

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  const renderCardHeader = (subtitle?: string) => (
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
      {subtitle && (
        <p className="mt-3 text-sm text-mid-gray">{subtitle}</p>
      )}
    </div>
  );

  // -------------------------------------------------------------------------
  // State: loading
  // -------------------------------------------------------------------------

  if (pageState === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white p-4">
        <div
          className="w-full max-w-md rounded-xl bg-white p-8 text-center"
          style={{ boxShadow: CARD_SHADOW }}
        >
          {renderCardHeader()}
          <p className="text-sm text-mid-gray">Verificando invitación...</p>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // State: invalid
  // -------------------------------------------------------------------------

  if (pageState === "invalid") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white p-4">
        <div
          className="w-full max-w-md rounded-xl bg-white p-8"
          style={{ boxShadow: CARD_SHADOW }}
        >
          {renderCardHeader()}
          <div className="rounded-lg bg-red-50 px-4 py-4 text-center">
            <p className="text-sm font-medium text-red-700">
              Invitación inválida o expirada
            </p>
            <p className="mt-2 text-sm text-red-600">
              Esta invitación ya fue utilizada o venció. Solicita una nueva al
              entrenador.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // State: success
  // -------------------------------------------------------------------------

  if (pageState === "success") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white p-4">
        <div
          className="w-full max-w-md rounded-xl bg-white p-8 text-center"
          style={{ boxShadow: CARD_SHADOW }}
        >
          {renderCardHeader()}
          <div className="rounded-lg bg-green-50 px-4 py-4">
            <p className="text-sm font-medium text-green-700">
              ¡Cuenta creada exitosamente!
            </p>
            <p className="mt-2 text-sm text-green-600">
              Ahora puedes iniciar sesión para ver el progreso de{" "}
              <span className="font-medium">{successName}</span>.
            </p>
          </div>
          <Link
            to="/login"
            className="mt-6 block w-full rounded-lg bg-charcoal px-4 py-2.5 text-center text-sm font-medium text-white transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            Ir al inicio de sesión
          </Link>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // State: form
  // -------------------------------------------------------------------------

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-4">
      <div
        className="w-full max-w-md rounded-xl bg-white p-8"
        style={{ boxShadow: CARD_SHADOW }}
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
          <p className="mt-3 text-base font-medium text-charcoal">
            Crear cuenta
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            Invitado para seguir a:{" "}
            <span className="font-medium text-charcoal">
              {tokenData?.athlete_name}
            </span>
          </p>
        </div>

        <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
          {/* Email — readonly */}
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
              readOnly
              value={tokenData?.email ?? ""}
              className="w-full cursor-not-allowed rounded-lg bg-surface px-3 py-2.5 text-sm text-mid-gray outline-none"
              style={{ boxShadow: INPUT_SHADOW }}
            />
          </div>

          {/* Nombre */}
          <div>
            <label
              htmlFor="first_name"
              className="mb-1.5 block text-sm font-medium text-charcoal"
            >
              Nombre
            </label>
            <input
              id="first_name"
              type="text"
              className={inputClassName}
              style={{ boxShadow: INPUT_SHADOW }}
              {...form.register("first_name")}
            />
            {form.formState.errors.first_name && (
              <p className="mt-1 text-xs text-red-600">
                {form.formState.errors.first_name.message}
              </p>
            )}
          </div>

          {/* Apellido */}
          <div>
            <label
              htmlFor="last_name"
              className="mb-1.5 block text-sm font-medium text-charcoal"
            >
              Apellido
            </label>
            <input
              id="last_name"
              type="text"
              className={inputClassName}
              style={{ boxShadow: INPUT_SHADOW }}
              {...form.register("last_name")}
            />
            {form.formState.errors.last_name && (
              <p className="mt-1 text-xs text-red-600">
                {form.formState.errors.last_name.message}
              </p>
            )}
          </div>

          {/* Contraseña */}
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
              className={inputClassName}
              style={{ boxShadow: INPUT_SHADOW }}
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <p className="mt-1 text-xs text-red-600">
                {form.formState.errors.password.message}
              </p>
            )}
          </div>

          {/* Teléfono — opcional */}
          <div>
            <label
              htmlFor="phone"
              className="mb-1.5 block text-sm font-medium text-charcoal"
            >
              Teléfono{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <input
              id="phone"
              type="tel"
              placeholder="Ej: +57 300 123 4567"
              className={inputClassName}
              style={{ boxShadow: INPUT_SHADOW }}
              {...form.register("phone")}
            />
          </div>

          {/* Server error */}
          {serverError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {serverError}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={form.formState.isSubmitting}
            className="w-full rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {form.formState.isSubmitting ? "Creando cuenta..." : "Crear cuenta"}
          </button>
        </form>
      </div>
    </div>
  );
}
