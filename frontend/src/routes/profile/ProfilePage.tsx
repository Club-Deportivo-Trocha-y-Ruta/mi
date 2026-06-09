/**
 * ProfilePage — Mi perfil / Configuración de cuenta.
 *
 * Tres secciones independientes:
 *  1. Información básica (nombre, apellido, teléfono)
 *  2. Cambiar contraseña
 *  3. Cambiar correo (verify-new-email-before-apply)
 *
 * Roles: todos los usuarios autenticados con can_login=true (admin, coach, parent).
 * Path: /perfil (ProtectedRoute sin restricción de rol).
 *
 * Convenciones:
 * - RHF + Zod, noValidate en cada formulario (sin HTML5 validation compitiendo).
 * - Toast inline (patrón del proyecto — AthleteNewsletterDetailPage).
 * - Inputs styled exactly like LoginPage / ForgotPasswordPage.
 * - Loading / error / empty states explícitos.
 */

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import {
  extractProfileError,
  useChangePassword,
  useProfile,
  useRequestEmailChange,
  useUpdateBasicInfo,
} from "@/hooks/profile/useProfile";
import type { ProfileOut } from "@/types/profile.types";

// ---------------------------------------------------------------------------
// Zod schemas
// ---------------------------------------------------------------------------

const basicSchema = z.object({
  first_name: z
    .string()
    .min(1, "El nombre es obligatorio")
    .max(100, "El nombre es demasiado largo"),
  last_name: z
    .string()
    .min(1, "El apellido es obligatorio")
    .max(100, "El apellido es demasiado largo"),
  phone: z
    .string()
    .max(20, "El teléfono es demasiado largo")
    .optional()
    .or(z.literal("")),
});

type BasicForm = z.infer<typeof basicSchema>;

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Ingresa tu contraseña actual"),
    new_password: z
      .string()
      .min(8, "La nueva contraseña debe tener al menos 8 caracteres"),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "Las contraseñas no coinciden",
    path: ["confirm_password"],
  });

type PasswordForm = z.infer<typeof passwordSchema>;

const emailSchema = z.object({
  current_password: z.string().min(1, "Ingresa tu contraseña actual"),
  new_email: z.string().email("Ingresa un correo válido"),
});

type EmailForm = z.infer<typeof emailSchema>;

// ---------------------------------------------------------------------------
// Shared style constants (project convention)
// ---------------------------------------------------------------------------

const labelClass = "mb-1.5 block text-sm font-medium text-charcoal";
const inputClass =
  "w-full rounded-lg bg-white px-3 py-2.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 min-h-[48px]";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";
const sectionStyle = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

// ---------------------------------------------------------------------------
// Toast inline component (matches AthleteNewsletterDetailPage pattern)
// ---------------------------------------------------------------------------

interface ToastBannerProps {
  type: "success" | "error";
  message: string;
  onDismiss: () => void;
}

function ToastBanner({ type, message, onDismiss }: ToastBannerProps) {
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-xl px-4 py-3 ${
        type === "success"
          ? "border border-green-200 bg-green-50"
          : "border border-red-200 bg-red-50"
      }`}
      role={type === "error" ? "alert" : "status"}
      data-testid={`toast-${type}`}
    >
      <p
        className={`text-sm ${type === "success" ? "text-green-800" : "text-red-700"}`}
      >
        {message}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className={`shrink-0 text-xs underline ${type === "success" ? "text-green-700" : "text-red-600"}`}
        aria-label="Cerrar notificación"
      >
        Cerrar
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 1: Basic information form
// ---------------------------------------------------------------------------

interface BasicInfoSectionProps {
  profile: ProfileOut;
}

function BasicInfoSection({ profile }: BasicInfoSectionProps) {
  const updateBasicInfo = useUpdateBasicInfo();
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const form = useForm<BasicForm>({
    resolver: zodResolver(basicSchema),
    defaultValues: {
      first_name: profile.first_name,
      last_name: profile.last_name,
      phone: profile.phone ?? "",
    },
  });

  // Keep form values in sync if profile data reloads (e.g., after save).
  useEffect(() => {
    form.reset({
      first_name: profile.first_name,
      last_name: profile.last_name,
      phone: profile.phone ?? "",
    });
  }, [profile.first_name, profile.last_name, profile.phone, form]);

  const onSubmit = async (values: BasicForm) => {
    setToast(null);
    try {
      await updateBasicInfo.mutateAsync({
        first_name: values.first_name,
        last_name: values.last_name,
        phone: values.phone || undefined,
      });
      setToast({
        type: "success",
        message: "Tu información fue actualizada correctamente.",
      });
    } catch (error) {
      setToast({ type: "error", message: extractProfileError(error) });
    }
  };

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4"
      style={sectionStyle}
      aria-labelledby="basic-info-title"
    >
      <div>
        <h2
          id="basic-info-title"
          className="text-base font-semibold text-charcoal"
        >
          Información básica
        </h2>
        <p className="mt-0.5 text-sm text-mid-gray">
          Actualiza tu nombre y teléfono de contacto.
        </p>
      </div>

      {/* Read-only: email + role */}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className={labelClass}>Correo</p>
          <p
            className="rounded-lg px-3 py-2.5 text-sm text-charcoal min-h-[48px] flex items-center"
            style={{ ...inputStyle, background: "#f9f9f9" }}
          >
            {profile.email ?? "—"}
          </p>
        </div>
        <div>
          <p className={labelClass}>Rol</p>
          <p
            className="rounded-lg px-3 py-2.5 text-sm text-charcoal capitalize min-h-[48px] flex items-center"
            style={{ ...inputStyle, background: "#f9f9f9" }}
          >
            {profile.role}
          </p>
        </div>
      </div>

      {toast && (
        <ToastBanner
          type={toast.type}
          message={toast.message}
          onDismiss={() => setToast(null)}
        />
      )}

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
        className="space-y-4"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="first_name" className={labelClass}>
              Nombre
            </label>
            <input
              id="first_name"
              type="text"
              autoComplete="given-name"
              className={inputClass}
              style={inputStyle}
              {...form.register("first_name")}
            />
            {form.formState.errors.first_name && (
              <p className={errorClass} role="alert">
                {form.formState.errors.first_name.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="last_name" className={labelClass}>
              Apellido
            </label>
            <input
              id="last_name"
              type="text"
              autoComplete="family-name"
              className={inputClass}
              style={inputStyle}
              {...form.register("last_name")}
            />
            {form.formState.errors.last_name && (
              <p className={errorClass} role="alert">
                {form.formState.errors.last_name.message}
              </p>
            )}
          </div>
        </div>

        <div>
          <label htmlFor="phone" className={labelClass}>
            Teléfono{" "}
            <span className="font-normal text-mid-gray">(opcional)</span>
          </label>
          <input
            id="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+57 300 000 0000"
            className={inputClass}
            style={inputStyle}
            {...form.register("phone")}
          />
          {form.formState.errors.phone && (
            <p className={errorClass} role="alert">
              {form.formState.errors.phone.message}
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={form.formState.isSubmitting}
            className="rounded-lg bg-charcoal px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 min-h-[48px]"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {form.formState.isSubmitting ? "Guardando..." : "Guardar cambios"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 2: Change password
// ---------------------------------------------------------------------------

function ChangePasswordSection() {
  const changePasswordMutation = useChangePassword();
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const form = useForm<PasswordForm>({
    resolver: zodResolver(passwordSchema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  });

  const onSubmit = async (values: PasswordForm) => {
    setToast(null);
    try {
      await changePasswordMutation.mutateAsync({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      setToast({
        type: "success",
        message: "Tu contraseña fue actualizada.",
      });
      form.reset();
    } catch (error) {
      setToast({ type: "error", message: extractProfileError(error) });
    }
  };

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4"
      style={sectionStyle}
      aria-labelledby="change-password-title"
    >
      <div>
        <h2
          id="change-password-title"
          className="text-base font-semibold text-charcoal"
        >
          Cambiar contraseña
        </h2>
        <p className="mt-0.5 text-sm text-mid-gray">
          Ingresa tu contraseña actual y elige una nueva.
        </p>
      </div>

      {toast && (
        <ToastBanner
          type={toast.type}
          message={toast.message}
          onDismiss={() => setToast(null)}
        />
      )}

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
        className="space-y-4"
      >
        <div>
          <label htmlFor="current_password" className={labelClass}>
            Contraseña actual
          </label>
          <input
            id="current_password"
            type="password"
            autoComplete="current-password"
            className={inputClass}
            style={inputStyle}
            {...form.register("current_password")}
          />
          {form.formState.errors.current_password && (
            <p className={errorClass} role="alert">
              {form.formState.errors.current_password.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="new_password" className={labelClass}>
            Nueva contraseña
          </label>
          <input
            id="new_password"
            type="password"
            autoComplete="new-password"
            className={inputClass}
            style={inputStyle}
            {...form.register("new_password")}
          />
          {form.formState.errors.new_password && (
            <p className={errorClass} role="alert">
              {form.formState.errors.new_password.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="confirm_password" className={labelClass}>
            Confirmar nueva contraseña
          </label>
          <input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            className={inputClass}
            style={inputStyle}
            {...form.register("confirm_password")}
          />
          {form.formState.errors.confirm_password && (
            <p className={errorClass} role="alert">
              {form.formState.errors.confirm_password.message}
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={form.formState.isSubmitting}
            className="rounded-lg bg-charcoal px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 min-h-[48px]"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {form.formState.isSubmitting
              ? "Actualizando..."
              : "Actualizar contraseña"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 3: Change email
// ---------------------------------------------------------------------------

function ChangeEmailSection() {
  const requestEmailChangeMutation = useRequestEmailChange();
  const [submitted, setSubmitted] = useState(false);
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const form = useForm<EmailForm>({
    resolver: zodResolver(emailSchema),
    defaultValues: {
      current_password: "",
      new_email: "",
    },
  });

  const onSubmit = async (values: EmailForm) => {
    setToast(null);
    try {
      await requestEmailChangeMutation.mutateAsync({
        current_password: values.current_password,
        new_email: values.new_email,
      });
      setSubmitted(true);
    } catch (error) {
      setToast({ type: "error", message: extractProfileError(error) });
    }
  };

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4"
      style={sectionStyle}
      aria-labelledby="change-email-title"
    >
      <div>
        <h2
          id="change-email-title"
          className="text-base font-semibold text-charcoal"
        >
          Cambiar correo
        </h2>
        <p className="mt-0.5 text-sm text-mid-gray">
          El cambio se aplicará solo después de confirmar el nuevo correo.
        </p>
      </div>

      {submitted ? (
        <p
          className="rounded-lg bg-green-50 px-3 py-3 text-sm text-green-800"
          role="status"
        >
          Revisa tu nuevo correo para confirmar el cambio. El correo actual
          permanece activo hasta que completes la confirmación.
        </p>
      ) : (
        <>
          {toast && (
            <ToastBanner
              type={toast.type}
              message={toast.message}
              onDismiss={() => setToast(null)}
            />
          )}

          <form
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
            className="space-y-4"
          >
            <div>
              <label
                htmlFor="email_current_password"
                className={labelClass}
              >
                Contraseña actual
              </label>
              <input
                id="email_current_password"
                type="password"
                autoComplete="current-password"
                className={inputClass}
                style={inputStyle}
                {...form.register("current_password")}
              />
              {form.formState.errors.current_password && (
                <p className={errorClass} role="alert">
                  {form.formState.errors.current_password.message}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="new_email" className={labelClass}>
                Nuevo correo
              </label>
              <input
                id="new_email"
                type="email"
                autoComplete="email"
                placeholder="nuevo@ejemplo.com"
                className={inputClass}
                style={inputStyle}
                {...form.register("new_email")}
              />
              {form.formState.errors.new_email && (
                <p className={errorClass} role="alert">
                  {form.formState.errors.new_email.message}
                </p>
              )}
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={form.formState.isSubmitting}
                className="rounded-lg bg-charcoal px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50 min-h-[48px]"
                style={{
                  boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
                }}
              >
                {form.formState.isSubmitting
                  ? "Enviando..."
                  : "Solicitar cambio de correo"}
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export function ProfilePage() {
  const { data: profile, isLoading, isError, error } = useProfile();

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-2">
      {/* Page title */}
      <div>
        <h1
          className="text-xl text-charcoal"
          style={{
            fontFamily: "'Cal Sans', system-ui, sans-serif",
            fontWeight: 600,
          }}
        >
          Mi perfil
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Gestiona tu información de cuenta.
        </p>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div
          className="rounded-xl bg-white p-8 text-center text-sm text-mid-gray"
          style={sectionStyle}
          role="status"
          aria-live="polite"
        >
          Cargando perfil...
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div
          className="rounded-xl bg-white p-8 text-center"
          style={sectionStyle}
          role="alert"
        >
          <p className="text-sm text-red-700">
            {extractProfileError(error)}
          </p>
        </div>
      )}

      {/* Content */}
      {profile && (
        <>
          <BasicInfoSection profile={profile} />
          <ChangePasswordSection />
          <ChangeEmailSection />
        </>
      )}
    </div>
  );
}
