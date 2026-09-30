import { isAxiosError } from "axios";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { CaptureReviewStep } from "@/components/athletes/anthropometry-capture/CaptureReviewStep";
import { QuickCaptureForm } from "@/components/athletes/anthropometry-capture/QuickCaptureForm";
import { PageHeader } from "@/components/shared/PageHeader";
import { RouteFallback } from "@/components/shared/RouteFallback";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry, useUpdateAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { formatDate } from "@/lib/datetime";
import {
  toAnthropometryPayload,
  type AnthropometryCaptureValues,
} from "@/schemas/anthropometryCapture.schema";
import type { AnthropometricRecord, PlausibilityMeasure } from "@/types/anthropometry.types";

export const NOT_AUTHOR_MESSAGE =
  "Solo quien tomó esta medición o un administrador puede modificarla.";
const OFFLINE_MESSAGE = "Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.";
const GENERIC_ERROR = "No se pudo guardar la medición. Intenta de nuevo.";
const SAME_DATE_MESSAGE =
  "Ya existe una medición de esta fecha. Elige otra fecha o corrige la medición existente.";
const TOO_YOUNG_MESSAGE =
  "Los pliegues cutáneos se miden desde los 9 años. Esta evaluación no admite medición.";

const QUICK_INPUT_ID: Record<PlausibilityMeasure, string> = {
  weight: "qc-weight",
  standing_height: "qc-standing",
  sitting_height: "qc-sitting",
  arm_span: "qc-arm-span",
};

function formatIsoDate(iso: string | null): string | null {
  if (!iso) return null;
  return formatDate(`${iso.slice(0, 10)}T12:00:00`) || null;
}

interface SaveErrorState {
  message: string;
  /** Solo los fallos de resultado incierto (red / 5xx) ofrecen «Reintentar». */
  retryable: boolean;
}

/** Mapea el error del PUT a la copia del contrato (mismas copias de pliegues que el 046). */
function describeUpdateError(err: unknown): SaveErrorState {
  if (!isAxiosError(err)) return { message: GENERIC_ERROR, retryable: true };
  const response = err.response;
  if (!response) return { message: OFFLINE_MESSAGE, retryable: true };
  if (response.status === 403) return { message: NOT_AUTHOR_MESSAGE, retryable: false };
  if (response.status === 409) {
    const detail = (response.data as { detail?: unknown } | undefined)?.detail;
    if (detail === "anthropometry_same_date_exists") {
      return { message: SAME_DATE_MESSAGE, retryable: false };
    }
    if (detail && typeof detail === "object") {
      const d = detail as {
        code?: unknown;
        previous_set_date?: unknown;
        next_allowed_date?: unknown;
      };
      if (d.code === "skinfold_interval_too_short") {
        const previous = formatIsoDate(
          typeof d.previous_set_date === "string" ? d.previous_set_date : null,
        );
        const next = formatIsoDate(
          typeof d.next_allowed_date === "string" ? d.next_allowed_date : null,
        );
        return {
          message:
            (previous
              ? `Ya hay una medición de pliegues reciente (${previous}). `
              : "Ya hay una medición de pliegues reciente. ") +
            "Entre dos mediciones debe pasar un intervalo mínimo para que el cambio sea confiable" +
            (next ? `: la siguiente puede tomarse desde el ${next}.` : "."),
          retryable: false,
        };
      }
      if (d.code === "athlete_too_young") return { message: TOO_YOUNG_MESSAGE, retryable: false };
    }
  }
  if (response.status >= 500) return { message: GENERIC_ERROR, retryable: true };
  return { message: GENERIC_ERROR, retryable: false };
}

function toFormDefaults(record: AnthropometricRecord): Partial<AnthropometryCaptureValues> {
  return {
    evaluation_date: record.evaluation_date.slice(0, 10),
    weight_kg: Number(record.weight_kg),
    standing_height_cm: Number(record.standing_height_cm),
    // En edición se muestra la talla NETA y el banco queda en 0.
    sitting_height_cm: Number(record.sitting_height_cm),
    bench_height_cm: 0,
    arm_span_cm: record.arm_span_cm == null ? null : Number(record.arm_span_cm),
    notes: record.notes ?? null,
  };
}

/**
 * AnthropometryEditPage — `/athletes/:id/anthropometry/:recordId/edit`
 * (feature 048, T024). Coach/admin (guard en `App.tsx`); el backend decide
 * quién puede modificar (`can_modify`, 403 `not_record_author`).
 */
export function AnthropometryEditPage() {
  const params = useParams<{ id: string; recordId: string }>();
  const navigate = useNavigate();
  const athleteId = Number(params.id);
  const recordId = Number(params.recordId);
  const validIds =
    Number.isFinite(athleteId) && athleteId > 0 && Number.isFinite(recordId) && recordId > 0;
  const profilePath = `/athletes/${athleteId}?tab=anthropometry`;

  const athleteQuery = useAthlete(athleteId, validIds);
  const recordsQuery = useAnthropometry(validIds ? athleteId : 0);
  const updateMutation = useUpdateAnthropometry(athleteId);

  const record = useMemo(
    () => recordsQuery.data?.find((r) => r.id === recordId) ?? null,
    [recordsQuery.data, recordId],
  );
  const defaults = useMemo(() => (record ? toFormDefaults(record) : undefined), [record]);

  const [reviewValues, setReviewValues] = useState<AnthropometryCaptureValues | null>(null);
  const [saveError, setSaveError] = useState<SaveErrorState | null>(null);

  const header = (
    <PageHeader
      title="Editar medición"
      subtitle={
        record ? `Medición del ${formatIsoDate(record.evaluation_date) ?? ""}` : undefined
      }
      backTo={{ to: profilePath, label: "Volver al perfil" }}
    />
  );

  if (validIds && (athleteQuery.isLoading || recordsQuery.isLoading)) {
    return <RouteFallback label="Cargando medición..." />;
  }

  const athlete = athleteQuery.data;
  if (!validIds || athleteQuery.isError || recordsQuery.isError || !athlete || !record) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <p role="alert" className="text-sm text-charcoal">
          {athleteQuery.isError || recordsQuery.isError
            ? "No se pudo cargar la medición. Revisa tu conexión e intenta de nuevo."
            : "No encontramos esta medición."}{" "}
          <Link to={profilePath} className="font-medium text-link-blue underline">
            Volver al perfil
          </Link>
        </p>
      </div>
    );
  }

  if (!record.can_modify) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <p role="alert" className="text-sm text-charcoal">
          {NOT_AUTHOR_MESSAGE}{" "}
          <Link to={profilePath} className="font-medium text-link-blue underline">
            Volver al perfil
          </Link>
        </p>
      </div>
    );
  }

  const save = () => {
    if (!reviewValues || updateMutation.isPending) return;
    setSaveError(null);
    updateMutation.mutate(
      { recordId, payload: toAnthropometryPayload(reviewValues) },
      {
        onSuccess: () => {
          toast.success("Medición actualizada.");
          navigate(profilePath);
        },
        onError: (err) => setSaveError(describeUpdateError(err)),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {header}
      <div className="flex flex-col gap-6 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline sm:p-6">
        <p className="text-sm text-mid-gray">
          Al guardar se recalculan el estado de maduración, los percentiles y la explicación de
          IA de esta medición.
        </p>
        {/* Cualquier cambio en la cuadrícula invalida el panel «Revisar». */}
        <div
          onChange={() => {
            if (reviewValues && !updateMutation.isPending) {
              setReviewValues(null);
              setSaveError(null);
            }
          }}
        >
          <QuickCaptureForm
            defaultValues={defaults}
            persistBench={false}
            isPending={updateMutation.isPending}
            onReview={(values) => {
              setSaveError(null);
              setReviewValues(values);
            }}
          />
        </div>
        {reviewValues && (
          <CaptureReviewStep
            mode="edit"
            athleteId={athleteId}
            athleteSex={athlete.sex}
            athleteBirthDate={athlete.birth_date}
            values={reviewValues}
            recordId={recordId}
            onRemeasure={(measure) => {
              setReviewValues(null);
              window.setTimeout(() => document.getElementById(QUICK_INPUT_ID[measure])?.focus(), 0);
            }}
            onSave={save}
            isSaving={updateMutation.isPending}
            saveError={saveError?.message ?? null}
            onRetry={saveError?.retryable ? save : undefined}
          />
        )}
      </div>
    </div>
  );
}

export default AnthropometryEditPage;
