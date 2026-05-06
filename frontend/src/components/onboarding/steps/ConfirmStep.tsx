/**
 * ConfirmStep — Paso 4 del wizard de onboarding (todos los roles).
 *
 * Muestra un resumen readonly de todos los datos ingresados antes de
 * crear la cuenta. No contiene campos editables.
 *
 * Lee datos de:
 *   - useFormContext(): campos del formulario (contraseña, perfil, consentimientos)
 *   - useOnboardingStore(): email, athleteName, clubName del token de invitación
 */

import { useFormContext } from "react-hook-form";

import type { OnboardingFormData } from "@/schemas/onboarding.schema";
import { useOnboardingStore } from "@/store/onboarding.store";
import { FamilyRelationship } from "@/types/enums";

// ---------------------------------------------------------------------------
// Constantes de presentación
// ---------------------------------------------------------------------------

const RELATIONSHIP_LABELS: Record<FamilyRelationship, string> = {
  [FamilyRelationship.padre]: "Padre",
  [FamilyRelationship.madre]: "Madre",
  [FamilyRelationship.acudiente]: "Acudiente",
};

const CONSENT_LABELS: Record<
  keyof Pick<
    OnboardingFormData,
    "accept_data_collection" | "accept_anthropometry"
  >,
  string
> = {
  accept_data_collection: "Datos básicos del atleta",
  accept_anthropometry: "Mediciones antropométricas (PHV)",
};

// ---------------------------------------------------------------------------
// Sub-componente: sección de resumen
// ---------------------------------------------------------------------------

interface SummarySectionProps {
  title: string;
  children: React.ReactNode;
}

function SummarySection({ title, children }: SummarySectionProps) {
  return (
    <div
      className="rounded-xl bg-white p-4"
      style={{
        boxShadow:
          "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 1px 3px 0px",
      }}
    >
      <h3
        className="mb-3 text-xs font-semibold uppercase tracking-wider text-mid-gray"
        aria-label={title}
      >
        {title}
      </h3>
      <dl className="space-y-2">{children}</dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: fila de dato
// ---------------------------------------------------------------------------

interface DataRowProps {
  label: string;
  value: string;
}

function DataRow({ label, value }: DataRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-xs text-mid-gray">{label}</dt>
      <dd className="truncate text-right text-sm font-medium text-charcoal">
        {value}
      </dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function ConfirmStep() {
  const { getValues } = useFormContext<OnboardingFormData>();
  const { email, athleteName, clubName } = useOnboardingStore();

  const values = getValues();

  // Nombre completo (solo si hay perfil de padre)
  const fullName =
    values.first_name && values.last_name
      ? `${values.first_name} ${values.last_name}`.trim()
      : null;

  // Parentesco con label legible
  const relationshipLabel =
    values.relationship_type
      ? RELATIONSHIP_LABELS[values.relationship_type] ?? values.relationship_type
      : null;

  // Consentimientos aceptados (solo los true)
  const acceptedConsents = (
    Object.keys(CONSENT_LABELS) as Array<keyof typeof CONSENT_LABELS>
  ).filter((key) => values[key] === true);

  return (
    <div className="space-y-4">
      {/* Sección 1: Datos de cuenta */}
      <SummarySection title="Datos de cuenta">
        <DataRow label="Correo electrónico" value={email ?? "—"} />
        <DataRow label="Contraseña" value="••••••••" />
      </SummarySection>

      {/* Sección 2: Datos personales (solo si hay perfil) */}
      {fullName && (
        <SummarySection title="Datos personales">
          <DataRow label="Nombre completo" value={fullName} />
          {values.phone && values.phone.length > 0 && (
            <DataRow label="Teléfono" value={values.phone} />
          )}
          {relationshipLabel && (
            <DataRow label="Rol" value={relationshipLabel} />
          )}
        </SummarySection>
      )}

      {/* Sección 3: Vinculación con atleta */}
      {(athleteName || clubName) && (
        <SummarySection title="Vinculación">
          <div className="rounded-lg bg-light-gray px-3 py-2.5">
            <p className="text-sm text-charcoal">
              Serás vinculado como{" "}
              <strong className="font-semibold">
                {relationshipLabel ?? "padre/acudiente"}
              </strong>{" "}
              de{" "}
              <strong className="font-semibold">
                {athleteName ?? "el atleta"}
              </strong>{" "}
              en{" "}
              <strong className="font-semibold">
                {clubName ?? "el club"}
              </strong>
              .
            </p>
          </div>
        </SummarySection>
      )}

      {/* Sección 4: Consentimientos aceptados */}
      {acceptedConsents.length > 0 && (
        <SummarySection title="Consentimientos aceptados">
          <ul className="space-y-1.5" aria-label="Lista de consentimientos aceptados">
            {acceptedConsents.map((key) => (
              <li key={key} className="flex items-center gap-2">
                <svg
                  className="h-3.5 w-3.5 shrink-0 text-green-600"
                  viewBox="0 0 14 14"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M2.5 7l3 3 6-6"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="text-sm text-charcoal">
                  {CONSENT_LABELS[key]}
                </span>
              </li>
            ))}
          </ul>
        </SummarySection>
      )}

      {/* Nota final */}
      <p className="px-1 text-center text-xs leading-relaxed text-mid-gray">
        Al crear tu cuenta, confirmas haber leído y aceptado los términos.{" "}
        <a
          href="/privacidad"
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-link-blue underline-offset-2 hover:underline"
          aria-label="Leer política de privacidad (se abre en nueva pestaña)"
        >
          Política de privacidad
        </a>
        .
      </p>
    </div>
  );
}
