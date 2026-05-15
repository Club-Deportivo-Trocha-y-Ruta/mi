/**
 * ConsentRenewalModal — Modal bloqueante de renovación de consentimiento parental.
 *
 * Se muestra cuando el padre tiene consentimiento desactualizado (is_current_policy=false)
 * o nunca dio consentimiento (current_consent=null) para alguno de sus atletas.
 *
 * El modal es INTENCIONALMENTE BLOQUEANTE: no se puede cerrar haciendo clic fuera
 * ni con Escape. El consentimiento es requisito legal (Ley 1581/2012) para continuar
 * usando la plataforma. La única salida alternativa es revocar (desvincularse).
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ExternalLink, Loader2, ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import { useRenewConsent } from "@/hooks/consent";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";
import { RevokeConsentDialog } from "./RevokeConsentDialog";

// ---------------------------------------------------------------------------
// Estilos del design system (Cal.com)
// ---------------------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  background: "rgba(19, 19, 22, 0.75)",
  backdropFilter: "blur(3px)",
};

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

const checkboxStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

const btnPrimaryStyle: React.CSSProperties = {
  boxShadow:
    "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(0, 0, 0, 0.16) 0px 1px 1.9px 0px inset, rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
};

const btnSecondaryStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

const changelogStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.05) 0px 1px 3px 0px",
};

// ---------------------------------------------------------------------------
// Schema de validación
// ---------------------------------------------------------------------------

/**
 * Los dos primeros checkboxes son obligatorios (z.literal(true)).
 * El tercero (IA) es opcional — z.boolean() con default false.
 */
const renewalSchema = z.object({
  accept_data_collection: z.literal(true, {
    error: "Debes aceptar el tratamiento de datos básicos del atleta para continuar",
  }),
  accept_anthropometry: z.literal(true, {
    error: "Debes aceptar el registro de medidas antropométricas para continuar",
  }),
  accept_third_party_sharing: z.boolean(),
});

type RenewalFormData = z.infer<typeof renewalSchema>;

// ---------------------------------------------------------------------------
// Sub-componente: ítem de consentimiento (espejo de ConsentStep.tsx)
// ---------------------------------------------------------------------------

interface ConsentItemProps {
  id: keyof RenewalFormData;
  label: string;
  description: string;
  error?: string;
  required?: boolean;
  register: ReturnType<typeof useForm<RenewalFormData>>["register"];
}

function ConsentItem({
  id,
  label,
  description,
  error,
  required = true,
  register,
}: ConsentItemProps) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 shrink-0">
        <input
          type="checkbox"
          id={`renewal-${id}`}
          className="h-4 w-4 cursor-pointer rounded accent-charcoal"
          style={checkboxStyle}
          {...register(id)}
          aria-required={required}
          aria-describedby={error ? `renewal-${id}-error` : undefined}
        />
      </div>
      <div className="flex-1 space-y-0.5">
        <label
          htmlFor={`renewal-${id}`}
          className="cursor-pointer text-sm font-medium text-charcoal"
        >
          {label}
        </label>
        <p className="text-xs leading-relaxed text-mid-gray">{description}</p>
        {error && (
          <p
            id={`renewal-${id}-error`}
            className="text-xs text-red-600"
            role="alert"
          >
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ConsentRenewalModalProps {
  athlete: AthleteConsentStatus;
  activePolicy: PrivacyPolicySummary;
  /** Callback cuando el padre completa la renovación para este atleta. */
  onRenewed: () => void;
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ConsentRenewalModal({
  athlete,
  activePolicy,
  onRenewed,
}: ConsentRenewalModalProps) {
  const [showRevokeDialog, setShowRevokeDialog] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { mutate: renew, isPending } = useRenewConsent();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RenewalFormData>({
    resolver: zodResolver(renewalSchema),
    defaultValues: {
      accept_data_collection: false as unknown as true,
      accept_anthropometry: false as unknown as true,
      accept_third_party_sharing: false,
    },
    mode: "onSubmit",
  });

  const onSubmit = handleSubmit((data) => {
    setServerError(null);

    renew(
      {
        athlete_id: athlete.athlete_id,
        policy_version: activePolicy.version,
        accept_data_collection: data.accept_data_collection,
        accept_anthropometry: data.accept_anthropometry,
        accept_third_party_sharing: data.accept_third_party_sharing ?? false,
      },
      {
        onSuccess: () => {
          onRenewed();
        },
        onError: () => {
          setServerError(
            "No fue posible guardar tu consentimiento. Intenta de nuevo.",
          );
        },
      },
    );
  });

  const isFirstConsent = athlete.current_consent === null;

  return (
    <>
      {/* Overlay bloqueante — ver docstring del módulo sobre por qué no puede cerrarse */}
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={overlayStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="renewal-modal-title"
        aria-describedby="renewal-modal-desc"
      >
        <div
          className="w-full max-w-lg rounded-2xl bg-white"
          style={cardStyle}
        >
          {/* Header */}
          <div className="px-6 pt-6 pb-4 border-b border-[rgba(34,42,53,0.08)]">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-link-blue/10">
                <ShieldCheck className="h-4 w-4 text-link-blue" aria-hidden="true" />
              </div>
              <div>
                <h2
                  id="renewal-modal-title"
                  className="text-base text-charcoal"
                  style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
                >
                  {isFirstConsent
                    ? "Consentimiento parental requerido"
                    : "Actualización de la política de privacidad"}
                </h2>
                <p
                  id="renewal-modal-desc"
                  className="mt-0.5 text-sm text-mid-gray"
                >
                  {isFirstConsent
                    ? `Para gestionar a ${athlete.athlete_name} en la plataforma, necesitamos tu autorización.`
                    : `Para continuar usando la plataforma con ${athlete.athlete_name}, necesitamos tu autorización a la nueva versión.`}
                </p>
              </div>
            </div>
          </div>

          {/* Cuerpo */}
          <form onSubmit={onSubmit}>
            <div className="px-6 py-5 space-y-5">
              {/* Versión de política */}
              <p className="text-xs text-mid-gray">
                Política{" "}
                <span className="font-medium text-charcoal">
                  {activePolicy.version}
                </span>
                {" "}— vigente desde{" "}
                {new Intl.DateTimeFormat("es-CO", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                }).format(new Date(`${activePolicy.effective_date}T12:00:00`))}
              </p>

              {/* Changelog (solo si existe y no es primer consentimiento) */}
              {!isFirstConsent && activePolicy.changelog && (
                <div
                  className="rounded-xl bg-light-gray px-4 py-3.5"
                  style={changelogStyle}
                >
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Qué cambió
                  </p>
                  <p className="text-sm text-charcoal leading-relaxed">
                    {activePolicy.changelog}
                  </p>
                </div>
              )}

              {/* Checkboxes de consentimiento */}
              <fieldset
                className="space-y-4"
                aria-label="Consentimientos parentales: dos obligatorios y uno opcional"
              >
                <legend className="sr-only">
                  Consentimientos parentales para {athlete.athlete_name}: dos
                  obligatorios y uno opcional de procesamiento con IA
                </legend>

                <ConsentItem
                  id="accept_data_collection"
                  label="Recolectar datos básicos del atleta"
                  description="Nombre, apellido, fecha de nacimiento y sexo, necesarios para gestionar la membresía del atleta en el club."
                  error={errors.accept_data_collection?.message}
                  register={register}
                />

                <div className="border-t border-border/50" aria-hidden="true" />

                <ConsentItem
                  id="accept_anthropometry"
                  label="Registrar mediciones antropométricas"
                  description="Talla de pie, talla sentado, peso, envergadura y cálculo de maduración biológica (PHV — Pico de Velocidad de Crecimiento) para llevar control del crecimiento del atleta y detectar señales de alerta nutricional o de desarrollo."
                  error={errors.accept_anthropometry?.message}
                  register={register}
                />

                <div className="border-t border-border/50" aria-hidden="true" />

                <ConsentItem
                  id="accept_third_party_sharing"
                  label="Procesamiento con IA (opcional)"
                  description="Autorizar al club a enviar la antropometría del atleta a Anthropic Claude o Google Gemini para generar explicaciones legibles sobre su desarrollo (estado PHV, crecimiento). Los datos no se usan para entrenar modelos. Puedes revocar en cualquier momento."
                  error={errors.accept_third_party_sharing?.message}
                  required={false}
                  register={register}
                />
              </fieldset>

              {/* Nota informativa */}
              <div
                className="flex gap-2.5 rounded-xl border border-link-blue/20 bg-link-blue/5 px-4 py-3"
                role="note"
                aria-label="Información sobre consentimientos"
              >
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-link-blue"
                  viewBox="0 0 16 16"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
                  <path
                    d="M8 5v4M8 11v.5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                <p className="text-xs text-mid-gray leading-relaxed">
                  Los dos primeros consentimientos son obligatorios para la participación
                  en el club. El de procesamiento con IA es opcional. Puedes revocar en
                  cualquier momento desde tu panel.
                </p>
              </div>

              {/* Error del servidor */}
              {serverError && (
                <p className="text-sm text-red-600" role="alert" aria-live="assertive">
                  {serverError}
                </p>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 pb-6 space-y-3">
              {/* Enlace a política completa */}
              <div className="flex justify-center">
                <a
                  href="/privacidad"
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(
                    "inline-flex items-center gap-1.5 text-xs font-medium text-link-blue",
                    "underline-offset-2 hover:underline",
                  )}
                  aria-label="Leer política de privacidad completa (se abre en nueva pestaña)"
                >
                  Leer política completa
                  <ExternalLink size={11} aria-hidden="true" />
                </a>
              </div>

              {/* Botones de acción */}
              <div className="flex justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setShowRevokeDialog(true)}
                  disabled={isPending}
                  className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-red-600 transition-opacity disabled:opacity-50"
                  style={btnSecondaryStyle}
                >
                  Revocar consentimiento
                </button>

                <button
                  type="submit"
                  disabled={isPending}
                  className="flex items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  style={btnPrimaryStyle}
                >
                  {isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  )}
                  {isPending ? "Guardando…" : "Aceptar nueva política"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Diálogo de revocación — se monta sobre el modal (z-index mayor) */}
      {showRevokeDialog && (
        <RevokeConsentDialog
          athlete={athlete}
          onClose={() => setShowRevokeDialog(false)}
          onSuccess={onRenewed}
        />
      )}
    </>
  );
}
