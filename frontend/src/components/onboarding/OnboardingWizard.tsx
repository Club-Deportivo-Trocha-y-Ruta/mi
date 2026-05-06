/**
 * OnboardingWizard — Wizard multi-paso para registro de padres y entrenadores.
 *
 * Flujo:
 *   1. Filtra los pasos visibles según el rol del usuario.
 *   2. Valida cada paso de forma granular con `trigger()` de RHF antes de avanzar.
 *   3. Persiste el estado del formulario en el Zustand store entre pasos.
 *   4. En el último paso, arma el payload y llama a useCompleteOnboarding().
 *   5. Limpia el store y dispara onSuccess(first_name) al registrarse exitosamente.
 *
 * Roles:
 *   - parent: account → parent-profile → consent → confirm
 *   - coach:  account → confirm
 */

import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FamilyRelationship } from "@/types/enums";
import {
  onboardingFormSchema,
  type OnboardingFormData,
} from "@/schemas/onboarding.schema";
import { useOnboardingStore } from "@/store/onboarding.store";
import {
  useCompleteOnboarding,
  type ParentOnboardingPayload,
} from "@/hooks/onboarding";
import {
  getStepsForRole,
  type OnboardingRole,
  type StepConfig,
} from "./onboarding-steps.config";
import { OnboardingStepper } from "./OnboardingStepper";
import { AccountStep } from "./steps/AccountStep";
import { ParentProfileStep } from "./steps/ParentProfileStep";
import { ConsentStep } from "./steps/ConsentStep";
import { ConfirmStep } from "./steps/ConfirmStep";

// ---------------------------------------------------------------------------
// Estilos del design system (Cal.com)
// ---------------------------------------------------------------------------

const cardStyle = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

const btnPrimaryStyle = {
  boxShadow:
    "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(0, 0, 0, 0.16) 0px 1px 1.9px 0px inset, rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
};

const btnSecondaryStyle = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface OnboardingWizardProps {
  role: OnboardingRole;
  tokenData: {
    token: string;
    email: string;
    athleteName: string;
    clubName: string;
  };
  /** Llamado al completar el registro exitosamente. Recibe el first_name. */
  onSuccess: (userName: string) => void;
}

// ---------------------------------------------------------------------------
// Mapa de campos por paso — para validación granular con trigger()
// ---------------------------------------------------------------------------

/**
 * Asocia cada step id con los campos del formulario que valida.
 * Permite llamar `methods.trigger(fields)` solo para los campos del paso actual.
 */
const STEP_FIELDS: Record<string, Array<keyof OnboardingFormData>> = {
  account: ["password", "password_confirm"],
  "parent-profile": ["first_name", "last_name", "phone", "relationship_type"],
  consent: ["accept_data_collection", "accept_anthropometry"],
  confirm: [],
};

// ---------------------------------------------------------------------------
// Helper: props específicas por step id
// ---------------------------------------------------------------------------

function buildStepProps(
  stepId: string,
  tokenData: OnboardingWizardProps["tokenData"],
): Record<string, unknown> {
  switch (stepId) {
    case "account":
      return { email: tokenData.email };
    case "consent":
      return {
        athleteName: tokenData.athleteName,
        clubName: tokenData.clubName,
      };
    default:
      return {};
  }
}

// ---------------------------------------------------------------------------
// Helper: renderizar el componente del paso actual
// ---------------------------------------------------------------------------

function renderStep(
  step: StepConfig,
  tokenData: OnboardingWizardProps["tokenData"],
): React.ReactNode {
  const props = buildStepProps(step.id, tokenData);

  switch (step.id) {
    case "account":
      return <AccountStep email={props.email as string} />;
    case "parent-profile":
      return <ParentProfileStep />;
    case "consent":
      return (
        <ConsentStep
          athleteName={props.athleteName as string}
          clubName={props.clubName as string}
        />
      );
    case "confirm":
      return <ConfirmStep />;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function OnboardingWizard({
  role,
  tokenData,
  onSuccess,
}: OnboardingWizardProps) {
  // -- Pasos filtrados por rol --
  const visibleSteps = getStepsForRole(role);

  // -- Store: paso actual y persistencia de datos --
  const store = useOnboardingStore();
  const currentStep = store.currentStep;

  // -- Mutation de registro --
  const { mutate, isPending, error: mutationError } = useCompleteOnboarding();

  // -- Formulario: validación granular por paso --
  const methods = useForm<OnboardingFormData>({
    resolver: zodResolver(onboardingFormSchema),
    defaultValues: { ...store.formData } as Partial<OnboardingFormData>,
    mode: "onTouched",
  });

  const isLastStep = currentStep === visibleSteps.length - 1;
  const currentStepConfig = visibleSteps[currentStep];

  // -- Avanzar al siguiente paso --
  const handleNext = async () => {
    const fieldsToValidate = STEP_FIELDS[currentStepConfig.id] ?? [];

    // Validación granular: solo los campos del paso actual
    // El paso "account" usa accountSchema con refine cross-field, pero
    // zodResolver del form completo aplica su propia validación al hacer trigger.
    const isValid =
      fieldsToValidate.length === 0
        ? true
        : await methods.trigger(fieldsToValidate);

    if (!isValid) return;

    // Persistir datos del paso en el store antes de avanzar
    store.updateFormData(methods.getValues() as Record<string, unknown>);
    store.setStep(currentStep + 1);
  };

  // -- Volver al paso anterior --
  const handleBack = () => {
    store.setStep(currentStep - 1);
  };

  // -- Enviar formulario en el último paso --
  const handleSubmit = methods.handleSubmit(async (data) => {
    // Combinar datos del form con datos del store para construir el payload.
    // El store puede contener datos de pasos previos que RHF no tiene montados
    // (ej: parent-profile al estar en el paso confirm). Se hace doble cast via
    // unknown porque el spread de Record<string,unknown> y FieldValues no solapa
    // estructuralmente con OnboardingFormData, aunque en runtime es correcto.
    const mergedData = ({
      ...store.formData,
      ...data,
    }) as unknown as OnboardingFormData;

    const payload: ParentOnboardingPayload = {
      token: tokenData.token,
      first_name: mergedData.first_name ?? "",
      last_name: mergedData.last_name ?? "",
      password: mergedData.password,
      phone: mergedData.phone || null,
      relationship_type: mergedData.relationship_type as FamilyRelationship,
      consent: {
        accept_data_collection: mergedData.accept_data_collection,
        accept_anthropometry: mergedData.accept_anthropometry,
      },
    };

    mutate(payload, {
      onSuccess: (out) => {
        store.reset();
        onSuccess(out.first_name);
      },
    });
  });

  // -- Acción del botón primario: avanzar o enviar --
  const handlePrimaryAction = isLastStep ? handleSubmit : handleNext;

  // -- Textos del botón primario --
  const primaryLabel = isLastStep ? "Crear cuenta" : "Siguiente";

  // -- Descripción del paso actual para el header --
  const stepDescriptions: Record<string, string> = {
    account: "Crea tu contraseña de acceso.",
    "parent-profile": "Ingresa tus datos personales.",
    consent: "Autoriza al club a gestionar los datos de tu hijo/a.",
    confirm: "Revisa todo antes de crear tu cuenta.",
  };

  return (
    <div
      className="w-full max-w-xl mx-auto overflow-hidden rounded-2xl bg-white"
      style={cardStyle}
    >
      {/* ---- Header: stepper ---- */}
      <div className="px-6 pt-6 pb-4 border-b border-[rgba(34,42,53,0.08)]">
        <OnboardingStepper steps={visibleSteps} currentStep={currentStep} />

        {/* Descripción del paso actual */}
        <p className="mt-3 text-sm text-mid-gray">
          {stepDescriptions[currentStepConfig?.id] ?? ""}
        </p>
      </div>

      {/* ---- Cuerpo: step component ---- */}
      <div className="px-6 py-5">
        <FormProvider {...methods}>
          {currentStepConfig ? renderStep(currentStepConfig, tokenData) : null}
        </FormProvider>
      </div>

      {/* ---- Footer: botones de navegación + error del servidor ---- */}
      <div className="px-6 pb-6 space-y-3">
        {/* Error del servidor */}
        {mutationError && (
          <div
            className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-4 py-3"
            role="alert"
            aria-live="assertive"
          >
            <AlertCircle
              className="mt-0.5 h-4 w-4 shrink-0 text-red-600"
              aria-hidden="true"
            />
            <p className="text-sm text-red-700">{mutationError.message}</p>
          </div>
        )}

        {/* Botones */}
        <div
          className={cn(
            "flex gap-3",
            currentStep === 0 ? "justify-end" : "justify-between",
          )}
        >
          {/* Botón "Anterior" — oculto en el primer paso */}
          {currentStep > 0 && (
            <button
              type="button"
              onClick={handleBack}
              disabled={isPending}
              className="flex items-center gap-1.5 rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50"
              style={btnSecondaryStyle}
              aria-label="Volver al paso anterior"
            >
              Anterior
            </button>
          )}

          {/* Botón primario: "Siguiente" o "Crear cuenta" */}
          <button
            type="button"
            onClick={handlePrimaryAction}
            disabled={isPending}
            className="flex items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            style={btnPrimaryStyle}
            aria-label={
              isLastStep
                ? "Crear cuenta y completar registro"
                : `Avanzar al paso ${currentStep + 2} de ${visibleSteps.length}`
            }
          >
            {isPending && (
              <Loader2
                className="h-4 w-4 animate-spin"
                aria-hidden="true"
              />
            )}
            {isPending ? "Creando cuenta…" : primaryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
