import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { Stepper, type StepperStep } from "@/components/shared/Stepper";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useFormDraft } from "@/hooks/useFormDraft";
import { useSaveSkinfolds } from "@/hooks/athletes/useBodyComposition";
import { formatDate } from "@/lib/datetime";
import { SKINFOLD_SITE_ORDER } from "@/lib/bodyComposition/siteDiagrams";
import {
  skinfoldWizardFormSchema,
  type SkinfoldWizardFormValues,
} from "@/schemas/bodyComposition.schema";
import { useAuthStore } from "@/store/auth.store";
import type { SkinfoldSetIn, SkinfoldSite, SkinfoldSiteIn } from "@/types/bodyComposition.types";

import { SkinfoldPrecheckStep } from "./SkinfoldPrecheckStep";
import { SkinfoldReviewStep } from "./SkinfoldReviewStep";
import { SkinfoldSiteStep } from "./SkinfoldSiteStep";

/**
 * SkinfoldWizard — asistente de captura de pliegues cutáneos (feature 046,
 * US1, T028).
 *
 * Pasos: pre-check → seis sitios (orden fijo del protocolo) → revisión.
 * Orquesta los componentes de paso (`SkinfoldPrecheckStep`,
 * `SkinfoldSiteStep`, `SkinfoldReviewStep`), que son controlados y no
 * conocen RHF: este componente es el único dueño del formulario.
 *
 * Contratos:
 * - Formulario RHF + `skinfoldWizardFormSchema` (T014); validación por paso
 *   con `trigger("sites.<sitio>")` antes de avanzar. Omitir un sitio nunca
 *   se valida ni se justifica (spec FR-002).
 * - Foco: mismo contrato que `SessionWizard` (`@/components/shared/Stepper`)
 *   — un efecto keyed en el paso activo enfoca el `<h2>` del paso con
 *   `tabIndex={-1}`. Los componentes de paso pintan su propio `<h2>`, así
 *   que el ref apunta al contenedor del paso y el efecto enfoca su `<h2>`.
 * - Borrador local: `useFormDraft` con target `skinfolds:{recordId}` y la
 *   misma copy de restaurar/descartar que el asistente de sesiones. Expira a
 *   las 24 h y se borra en logout (FR-008, privacy-audit F8, T081): se
 *   ofrece solo dentro del mismo día, hasta que se guarda o se descarta.
 *   Sólo se autoguarda cuando hay progreso real (alguna lectura u omisión),
 *   para no ofrecer como "borrador" un formulario en blanco.
 * - "Hoy prefiere no medirse" (pre-check) arma el set con los seis sitios
 *   `{declined: true}` y lo envía directamente, sin pasar por los pasos de
 *   sitio y sin pedir motivo.
 * - Errores: 409 de intervalo → explicación con `next_allowed_date`; sin
 *   respuesta del servidor → mensaje offline con reintento (y reintento
 *   automático al recuperar la conexión); el borrador se conserva.
 *
 * Privacidad: el borrador contiene lecturas de un menor — vive sólo en el
 * dispositivo del entrenador bajo una clave aislada por usuario, se borra al
 * guardar o descartar y nunca se registra en logs.
 */
export interface SkinfoldWizardProps {
  athleteId: number;
  recordId: number;
  /** Edad del deportista en la fecha de la evaluación (rango plausible por sitio). */
  ageYears: number;
  /** Se invoca tras un guardado exitoso (set medido o totalmente declinado). */
  onDone?: (outcome: { declinedAll: boolean }) => void;
}

type WizardFormInput = z.input<typeof skinfoldWizardFormSchema>;

const PRECHECK_STEP = 0;
const FIRST_SITE_STEP = 1;
const REVIEW_STEP = SKINFOLD_SITE_ORDER.length + 1;

const SITE_LABEL_ES: Record<SkinfoldSite, string> = {
  triceps: "Tríceps",
  biceps: "Bíceps",
  subscapular: "Subescapular",
  medial_calf: "Pantorrilla",
  iliac_crest: "Cresta ilíaca",
  supraspinale: "Supraespinal",
};

const STEPS: StepperStep[] = [
  { label: "Preparación" },
  ...SKINFOLD_SITE_ORDER.map((site) => ({ label: SITE_LABEL_ES[site] })),
  { label: "Revisar" },
];

const OFFLINE_MESSAGE = "Sin conexión: se guardará cuando vuelvas a tener señal";
const GENERIC_ERROR = "No se pudo guardar la medición. Intenta de nuevo.";
const READINGS_ERROR =
  "Revisa las lecturas: se necesitan dos (o tres) valores entre 2 y 60 mm, en pasos de 0,5 mm.";

function emptySites(): SkinfoldWizardFormValues["sites"] {
  return Object.fromEntries(
    SKINFOLD_SITE_ORDER.map((site) => [site, { declined: false, readings: [] }]),
  ) as unknown as SkinfoldWizardFormValues["sites"];
}

function defaultValues(): WizardFormInput {
  return { caliper_model: "slim_guide", sites: emptySites() };
}

function hasProgress(values: WizardFormInput): boolean {
  const sites = values.sites ?? {};
  return Object.values(sites).some(
    (site) => !!site && (site.declined === true || (site.readings?.length ?? 0) > 0),
  );
}

function toPayload(values: WizardFormInput): SkinfoldSetIn {
  const sites = Object.fromEntries(
    SKINFOLD_SITE_ORDER.map((site): [SkinfoldSite, SkinfoldSiteIn] => {
      const value = values.sites[site];
      return value.declined ? [site, { declined: true }] : [site, { readings: [...value.readings] }];
    }),
  ) as Record<SkinfoldSite, SkinfoldSiteIn>;
  return { caliper_model: values.caliper_model ?? "slim_guide", sites };
}

function allDeclinedPayload(caliperModel: string): SkinfoldSetIn {
  const sites = Object.fromEntries(
    SKINFOLD_SITE_ORDER.map((site) => [site, { declined: true }]),
  ) as Record<SkinfoldSite, SkinfoldSiteIn>;
  return { caliper_model: caliperModel, sites };
}

/** "2026-12-19" → "19 de diciembre de 2026" (fecha pura, sin desfase de zona). */
function formatIsoDate(iso: string | null): string | null {
  if (!iso) return null;
  // Mediodía naive (= UTC) cae el mismo día en Bogotá (UTC−5).
  return formatDate(`${iso.slice(0, 10)}T12:00:00`) || null;
}

type SubmitError =
  | { kind: "offline" }
  | { kind: "interval"; previousDate: string | null; nextDate: string | null }
  | { kind: "too_young" }
  | { kind: "other"; message: string };

function classifySubmitError(err: unknown): SubmitError {
  const response = (err as { response?: { status?: number; data?: { detail?: unknown } } } | null)
    ?.response;
  // Sin respuesta del servidor (red caída, señal intermitente en campo).
  if (!response) return { kind: "offline" };

  const detail = response.data?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as {
      code?: unknown;
      message?: unknown;
      previous_set_date?: unknown;
      next_allowed_date?: unknown;
    };
    if (d.code === "skinfold_interval_too_short") {
      return {
        kind: "interval",
        previousDate: typeof d.previous_set_date === "string" ? d.previous_set_date : null,
        nextDate: typeof d.next_allowed_date === "string" ? d.next_allowed_date : null,
      };
    }
    if (d.code === "athlete_too_young") return { kind: "too_young" };
    if (typeof d.message === "string" && d.message.trim()) {
      return { kind: "other", message: d.message };
    }
  }
  if (typeof detail === "string" && detail.trim()) return { kind: "other", message: detail };
  return { kind: "other", message: GENERIC_ERROR };
}

export function SkinfoldWizard({ athleteId, recordId, ageYears, onDone }: SkinfoldWizardProps) {
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const saveMutation = useSaveSkinfolds(athleteId, recordId);

  const {
    getValues,
    setValue,
    trigger,
    watch,
    reset,
    clearErrors,
    formState: { errors },
  } = useForm<WizardFormInput, unknown, SkinfoldWizardFormValues>({
    resolver: zodResolver(skinfoldWizardFormSchema),
    defaultValues: defaultValues(),
    mode: "onSubmit",
  });

  const [step, setStep] = useState(PRECHECK_STEP);
  // Remonta el paso de sitio tras restaurar un borrador: `SkinfoldSiteStep`
  // inicializa sus campos de texto desde `value` sólo al montar.
  const [restoreNonce, setRestoreNonce] = useState(0);
  const [submitError, setSubmitError] = useState<SubmitError | null>(null);
  const lastPayloadRef = useRef<{ payload: SkinfoldSetIn; declinedAll: boolean } | null>(null);

  // --- Foco (contrato de `@/components/shared/Stepper`) ----------------------
  const stepContainerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const heading = stepContainerRef.current?.querySelector<HTMLHeadingElement>("h2");
    if (!heading) return;
    heading.tabIndex = -1;
    heading.focus();
  }, [step, restoreNonce]);

  // --- Borrador local ---------------------------------------------------------
  const { restoreCandidate, saveDraft, clearDraft } = useFormDraft<WizardFormInput>({
    userId,
    target: `skinfolds:${recordId}`,
    debounceMs: 300,
  });
  const [draftDismissed, setDraftDismissed] = useState(false);

  const watched = watch();
  const lastSerialized = useRef<string>("");
  useEffect(() => {
    if (!hasProgress(watched)) return;
    const serialized = JSON.stringify({ watched, step });
    if (serialized !== lastSerialized.current) {
      lastSerialized.current = serialized;
      saveDraft(watched, step);
    }
  }, [watched, step, saveDraft]);

  function restoreDraft() {
    if (restoreCandidate) {
      reset({ ...defaultValues(), ...restoreCandidate.values });
      setStep(Math.min(Math.max(restoreCandidate.step, PRECHECK_STEP), REVIEW_STEP));
      setRestoreNonce((n) => n + 1);
    }
    setDraftDismissed(true);
  }

  function discardDraft() {
    clearDraft();
    setDraftDismissed(true);
  }

  // --- Envío -------------------------------------------------------------------
  const submit = useCallback(
    async (payload: SkinfoldSetIn, declinedAll: boolean) => {
      lastPayloadRef.current = { payload, declinedAll };
      setSubmitError(null);
      try {
        await saveMutation.mutateAsync(payload);
        clearDraft();
        lastPayloadRef.current = null;
        onDone?.({ declinedAll });
      } catch (err) {
        // El borrador se conserva: nada de lo capturado se pierde.
        setSubmitError(classifySubmitError(err));
      }
    },
    [saveMutation, clearDraft, onDone],
  );

  function retry() {
    if (lastPayloadRef.current) {
      void submit(lastPayloadRef.current.payload, lastPayloadRef.current.declinedAll);
    }
  }

  // Reintento automático al recuperar la señal.
  const isOffline = submitError?.kind === "offline";
  useEffect(() => {
    if (!isOffline || typeof window === "undefined") return;
    const onOnline = () => {
      if (lastPayloadRef.current) {
        void submit(lastPayloadRef.current.payload, lastPayloadRef.current.declinedAll);
      }
    };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [isOffline, submit]);

  function handleDeclineAll() {
    void submit(allDeclinedPayload(getValues("caliper_model") ?? "slim_guide"), true);
  }

  async function handleReviewSubmit() {
    const valid = await trigger();
    if (!valid) {
      // Lleva al primer sitio inválido para corregirlo.
      const firstInvalid = SKINFOLD_SITE_ORDER.findIndex(
        (site) => !!getValues(`sites.${site}`) && !isSiteValid(getValues(`sites.${site}`)),
      );
      if (firstInvalid >= 0) setStep(FIRST_SITE_STEP + firstInvalid);
      return;
    }
    void submit(toPayload(getValues()), false);
  }

  // --- Navegación ---------------------------------------------------------------
  const currentSite: SkinfoldSite | null =
    step >= FIRST_SITE_STEP && step < REVIEW_STEP
      ? SKINFOLD_SITE_ORDER[step - FIRST_SITE_STEP]
      : null;

  async function goNext() {
    if (currentSite) {
      const valid = await trigger(`sites.${currentSite}`);
      if (!valid) return;
    }
    setStep((s) => Math.min(s + 1, REVIEW_STEP));
  }

  function goBack() {
    if (currentSite) clearErrors(`sites.${currentSite}`);
    setStep((s) => Math.max(s - 1, PRECHECK_STEP));
  }

  function skipCurrentSite() {
    if (!currentSite) return;
    clearErrors(`sites.${currentSite}`);
    setStep((s) => Math.min(s + 1, REVIEW_STEP));
  }

  const siteError = currentSite ? errors.sites?.[currentSite] : undefined;
  const isSubmitting = saveMutation.isPending;
  const showRestoreBanner = !!restoreCandidate && !draftDismissed;

  return (
    <section className="flex flex-col gap-4" data-testid="skinfold-wizard">
      <Stepper
        steps={STEPS}
        active={step}
        onStepClick={(index) => setStep(index)}
        ariaLabel="Pasos de la medición de pliegues"
      />

      {showRestoreBanner && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900"
          data-testid="skinfold-draft-banner"
        >
          <span>Tienes un borrador sin guardar de esta medición.</span>
          <div className="flex gap-2">
            <Button type="button" size="lg" onClick={restoreDraft}>
              Restaurar
            </Button>
            <Button type="button" variant="secondary" size="lg" onClick={discardDraft}>
              Descartar
            </Button>
          </div>
        </div>
      )}

      {submitError && <SubmitErrorAlert error={submitError} onRetry={retry} retrying={isSubmitting} />}

      <div
        ref={stepContainerRef}
        className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline [&_h2]:outline-none [&_h2:focus-visible]:ring-2 [&_h2:focus-visible]:ring-link-blue/50"
      >
        {step === PRECHECK_STEP && (
          <SkinfoldPrecheckStep
            onNext={() => setStep(FIRST_SITE_STEP)}
            onDeclineAll={handleDeclineAll}
            isDeclining={isSubmitting}
          />
        )}

        {currentSite && (
          <div className="flex flex-col gap-6">
            <SkinfoldSiteStep
              key={`${currentSite}-${restoreNonce}`}
              site={currentSite}
              ageYears={ageYears}
              value={watched.sites[currentSite]}
              onChange={(value) =>
                setValue(`sites.${currentSite}`, value, { shouldDirty: true })
              }
              onSkip={skipCurrentSite}
              stepLabel={`Sitio ${step - FIRST_SITE_STEP + 1} de ${SKINFOLD_SITE_ORDER.length}`}
            />
            {siteError && (
              <p role="alert" className="text-sm text-danger">
                {READINGS_ERROR}
              </p>
            )}
            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
              <Button type="button" variant="secondary" size="lg" onClick={goBack}>
                Atrás
              </Button>
              <Button type="button" size="lg" onClick={() => void goNext()}>
                Siguiente
              </Button>
            </div>
          </div>
        )}

        {step === REVIEW_STEP && (
          <div className="flex flex-col gap-6">
            <SkinfoldReviewStep
              sites={watched.sites as SkinfoldWizardFormValues["sites"]}
              onSubmit={() => void handleReviewSubmit()}
              isSubmitting={isSubmitting}
            />
            <div className="flex">
              <Button type="button" variant="secondary" size="lg" onClick={goBack}>
                Atrás
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function isSiteValid(site: WizardFormInput["sites"][SkinfoldSite]): boolean {
  if (site.declined) return true;
  return skinfoldWizardFormSchema.shape.sites.shape.triceps.safeParse(site).success;
}

function SubmitErrorAlert({
  error,
  onRetry,
  retrying,
}: {
  error: SubmitError;
  onRetry: () => void;
  retrying: boolean;
}) {
  if (error.kind === "offline") {
    return (
      <Alert variant="warning" data-testid="skinfold-offline">
        <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
          <span>{OFFLINE_MESSAGE}</span>
          <Button type="button" variant="secondary" size="lg" onClick={onRetry} disabled={retrying}>
            Reintentar
          </Button>
        </AlertDescription>
      </Alert>
    );
  }
  if (error.kind === "interval") {
    const previous = formatIsoDate(error.previousDate);
    const next = formatIsoDate(error.nextDate);
    return (
      <Alert variant="warning" data-testid="skinfold-interval">
        <AlertDescription>
          {previous
            ? `Ya hay una medición de pliegues reciente (${previous}). `
            : "Ya hay una medición de pliegues reciente. "}
          Entre dos mediciones debe pasar un intervalo mínimo para que el cambio sea
          confiable
          {next ? `: la siguiente puede tomarse desde el ${next}.` : "."}
        </AlertDescription>
      </Alert>
    );
  }
  if (error.kind === "too_young") {
    return (
      <Alert variant="warning">
        <AlertDescription>
          Los pliegues cutáneos se miden desde los 9 años. Esta evaluación no admite medición.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant="destructive">
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}
