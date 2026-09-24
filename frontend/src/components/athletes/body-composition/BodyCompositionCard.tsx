/**
 * BodyCompositionCard — resumen de composición corporal por pliegues
 * cutáneos en el tab de crecimiento del coach (feature 046, US2, T038),
 * per `contracts/body-composition-reading.md` §4 y
 * `contracts/skinfolds-api.md`.
 *
 * Alimentado por `useBodyComposition(athleteId)` (T037) — un
 * `GET .../body-composition` propio, no el bloque `body_composition` de
 * `useGrowthSummary` (ese es el que consumirían boletín/tarjetas de
 * familia). Mismo patrón de manejo de estado que `GrowthStatusRow`/
 * `NextMeasurementCard`: puramente presentacional, la query ya resuelta se
 * pasa desde `GrowthTab.tsx`.
 *
 * Privacidad (Ley 1581): sólo cifras y fechas de un menor — nunca nombre.
 */
import { Ruler } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";

import { Sparkline } from "@/components/athletes/growth/Sparkline";
import { FieldGuideDownloadButton } from "@/components/athletes/body-composition/FieldGuideDownloadButton";
import { ReferralNoteButton } from "@/components/athletes/body-composition/ReferralNoteButton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { StatCard } from "@/components/shared/StatCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { Status } from "@/components/shared/StatusBadge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { BODY_COMPOSITION_COACH_LABELS, getBodyCompositionBandTone } from "@/lib/growth/bands";
import type {
  BandReasonCode,
  BodyCompositionOut,
  CoachBand,
  LegMissing,
  SkinfoldSetOut,
  SumChangeCode,
} from "@/types/bodyComposition.types";

export interface BodyCompositionCardProps {
  query: UseQueryResult<BodyCompositionOut, Error>;
  /** CTA "Ver detalle por sitio" — abre `BodyCompositionDetailDialog` (T039). */
  onViewDetail?: () => void;
}

/**
 * Mirror de `Settings.body_comp_mdc_sum4_mm` (`backend/app/config.py`,
 * default 7.0 mm) — el umbral de cambio mínimo detectable en Σ4. La API no
 * lo devuelve (sólo el código ya clasificado y el delta), así que se
 * duplica aquí para renderizar la frase exacta de
 * `contracts/body-composition-reading.md` §4 ("Change reading"), mismo
 * criterio que `NextMeasurementCard.tsx::INTERVAL_TO_STAGE`.
 */
const SUM4_MDC_MM = 7.0;

/**
 * Mirror de `backend/app/services/body_composition.py::COACH_REASON_COPY`
 * (contrato §4 "Coach") — la API no envía el texto ya armado, sólo el
 * código (`reading.band_reason_code`); mismo criterio de duplicación que
 * `SUM4_MDC_MM` arriba.
 */
const COACH_REASON_COPY: Record<BandReasonCode, string> = {
  no_real_change:
    "Sin cambio real en la suma de pliegues desde la última toma (dentro del margen de medición).",
  expected_pubertal_gain:
    "La suma de pliegues subió de forma real, con peso y talla creciendo dentro de lo esperado: patrón habitual alrededor del pico de crecimiento en niñas.",
  pre_spurt_accumulation:
    "La suma de pliegues subió de forma real con la talla creciendo a ritmo esperado: acumulación previa al estirón, frecuente en esta etapa.",
  post_phv_lean_gain:
    "Peso arriba con pliegues estables o a la baja después del pico de crecimiento: ganancia de masa magra esperada.",
  first_set:
    "Primera toma de pliegues: hace falta una segunda toma (≥ 90 días) para leer una tendencia.",
  stable: "Composición corporal estable respecto a la toma anterior.",
  sum_up_unexplained:
    "La suma de pliegues subió más allá del margen sin un patrón de crecimiento que lo explique: vale una conversación en privado, sin cifras.",
  sum_up_velocity_low:
    "La suma de pliegues subió de forma real mientras la velocidad de talla está por debajo de lo esperado: conversa en privado y revisa en la próxima toma.",
  sum_down_unexplained:
    "La suma de pliegues bajó más allá del margen con el peso estancado; falta confirmar el crecimiento en talla para leer el patrón.",
  reference_extreme:
    "Un pliegue está en el extremo de la referencia poblacional (≤ P5 o ≥ P95): es contexto, no un veredicto; observa la tendencia en la próxima toma.",
  bmi_z_drop:
    "El índice de masa corporal para la edad cayó más de una desviación estándar: conversa con la familia y revisa alimentación con enfoque «comida primero».",
  velocity_low_persistent:
    "La velocidad de talla lleva dos ciclos por debajo de lo esperado: revisa junto con la composición corporal y considera consultar.",
  energy_availability_pattern:
    "Patrón combinado: la suma de pliegues cayó más allá del margen, el peso se estancó y la talla sigue creciendo. Compatible con baja disponibilidad energética. No es un diagnóstico: conversa con la familia en lenguaje neutro y considera remitir a un profesional de salud.",
};

/**
 * Mirror de `backend/app/services/body_composition.py::ESCALATION_COPY` —
 * sólo ámbar/rojo tienen sugerencia de escalamiento (verde no trae fila).
 */
const ESCALATION_COPY: Partial<Record<CoachBand, string>> = {
  ambar:
    "Sugerencia: conversa en privado con el/la deportista y la familia, sin mencionar números ni porcentajes. Si el patrón se repite en la próxima toma o aparecen otras señales (fatiga persistente, cambios de ánimo, enfermedad frecuente), pasa a seguimiento con la familia.",
  rojo: "Esto NO es un diagnóstico. Conversa con la familia en lenguaje neutro (nunca calorías ni peso frente al/a la deportista) y coordina la remisión a un profesional de salud con la nota de remisión.",
};

/** Etiquetas en español de cada `LegMissing` para la línea "No evaluado: …". */
const LEG_MISSING_LABELS: Record<LegMissing, string> = {
  weight: "peso",
  height: "talla",
  velocity: "velocidad de talla",
  bmi_z: "índice de masa corporal",
  reference: "referencia poblacional",
  previous_set: "toma anterior",
};

const MONTHS_ES_SHORT = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/** Igual a `NextMeasurementCard.tsx::formatDueDate` — fecha corta es-CO sin desfase de huso. */
function formatDueDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const label = MONTHS_ES_SHORT[Number(month) - 1] ?? month;
  return `${Number(day)} ${label} ${year}`;
}

function formatMm(value: number): string {
  return `${value.toFixed(1)} mm`;
}

function formatSignedMm(value: number): string {
  return value >= 0 ? `+${value.toFixed(1)} mm` : `${value.toFixed(1)} mm`;
}

interface ChangeCopy {
  label: string;
  tone: Status;
}

/** `contracts/body-composition-reading.md` §4 "Change reading (coach card)". */
export function changeReadingCopy(
  code: SumChangeCode,
  deltaMm: number | null,
): ChangeCopy {
  if (code === "none" || deltaMm === null) {
    return { label: "Sin toma anterior comparable", tone: "neutral" };
  }
  const threshold = SUM4_MDC_MM.toFixed(1);
  const delta = formatSignedMm(deltaMm);
  if (code === "within_noise") {
    return {
      label: `Dentro del margen de medición (${delta}; umbral ${threshold} mm)`,
      tone: "neutral",
    };
  }
  return {
    label: `Cambio real (${delta}; umbral ${threshold} mm)`,
    tone: "warning",
  };
}

/** Último set por `evaluation_date` — `sets`/`series` no garantizan un orden fijo entre sí. */
function latestSetOf(sets: SkinfoldSetOut[]): SkinfoldSetOut | undefined {
  return [...sets].sort((a, b) => b.evaluation_date.localeCompare(a.evaluation_date))[0];
}

/** FR spec.md §71: "falta tríceps" / "falta pantorrilla" cuando falta un insumo de la ecuación. */
function estimateMissingReason(set: SkinfoldSetOut | undefined): string | null {
  if (!set) return null;
  if (set.sites.triceps.declined) return "Falta tríceps para estimar % grasa";
  if (set.sites.medial_calf.declined) return "Falta pantorrilla para estimar % grasa";
  return null;
}

function BodyCompositionSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando composición corporal…"
      className="grid gap-3 sm:grid-cols-2"
    >
      <StatCard label="Suma de 4 pliegues (Σ4)" value="" isLoading />
      <StatCard label="Masa libre de grasa (est.)" value="" isLoading />
    </div>
  );
}

export function BodyCompositionCard({ query, onViewDetail }: BodyCompositionCardProps) {
  if (query.isLoading) {
    return <BodyCompositionSkeleton />;
  }

  if (query.isError) {
    return (
      <ErrorState
        message="No se pudo cargar la composición corporal."
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }

  const data = query.data;

  if (!data || data.sets.length === 0) {
    return (
      <EmptyState
        icon={Ruler}
        title="Aún no hay pliegues registrados"
        description="La suma de pliegues y las estimaciones aparecen aquí en cuanto el coach registre la primera toma."
      />
    );
  }

  const { series, reading, estimates_latest, next_due_date } = data;
  const sum4Values = series?.sum4.map((p) => p.value) ?? [];
  const sum6Values = series?.sum6.map((p) => p.value) ?? [];
  const latestSum4 = sum4Values.length > 0 ? sum4Values[sum4Values.length - 1] : null;
  const latestSum6 = sum6Values.length > 0 ? sum6Values[sum6Values.length - 1] : null;
  const set = latestSetOf(data.sets);

  const change = reading
    ? changeReadingCopy(reading.sum_change_code, reading.sum4_change_mm)
    : null;

  const bodyFatPct = estimates_latest?.body_fat_pct ?? null;
  const marginPct = estimates_latest?.margin_pct ?? 4;
  const missingReason = bodyFatPct === null ? estimateMissingReason(set) : null;

  return (
    <div data-testid="body-composition-card" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-charcoal">Composición corporal</h3>
        <FieldGuideDownloadButton />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <StatCard
          label="Suma de 4 pliegues (Σ4)"
          value={latestSum4 !== null ? formatMm(latestSum4) : "—"}
          hint={latestSum6 !== null ? `Σ6: ${formatMm(latestSum6)}` : undefined}
          badge={
            <div className="flex flex-col gap-2">
              {change && <StatusBadge status={change.tone} label={change.label} />}
              {sum4Values.length >= 2 && (
                <Sparkline
                  values={sum4Values}
                  ariaLabel={`Evolución de la suma de 4 pliegues, últimas ${sum4Values.length} tomas`}
                />
              )}
            </div>
          }
        />
        <StatCard
          label="Masa libre de grasa (est.)"
          value={
            estimates_latest?.fat_free_mass_kg != null
              ? `${estimates_latest.fat_free_mass_kg.toFixed(1)} kg`
              : "—"
          }
          hint={
            bodyFatPct !== null
              ? `% grasa (est.) ${bodyFatPct.toFixed(1)}% — estimado (±${marginPct} puntos)`
              : (missingReason ?? "Sin estimación disponible")
          }
        />
      </div>

      {next_due_date && (
        <p className="text-sm text-charcoal" data-testid="body-composition-next-due">
          Próxima toma de pliegues: {formatDueDate(next_due_date)}
        </p>
      )}

      {reading && (
        <div className="space-y-2" data-testid="body-composition-band">
          <StatusBadge
            status={getBodyCompositionBandTone(reading.band)}
            label={BODY_COMPOSITION_COACH_LABELS[reading.band]}
          />

          <p className="text-sm text-charcoal">{COACH_REASON_COPY[reading.band_reason_code]}</p>

          {reading.legs_missing.length > 0 && (
            <p className="text-sm text-mid-gray">
              No evaluado: {reading.legs_missing.map((leg) => LEG_MISSING_LABELS[leg]).join(", ")}
            </p>
          )}

          {ESCALATION_COPY[reading.band] && (
            <Alert
              variant={reading.band === "rojo" ? "destructive" : "warning"}
              data-testid="body-composition-escalation"
            >
              <AlertDescription>{ESCALATION_COPY[reading.band]}</AlertDescription>
            </Alert>
          )}

          {reading.band === "rojo" && <ReferralNoteButton athleteId={data.athlete_id} />}
        </div>
      )}

      {onViewDetail && (
        <Button type="button" variant="outline" size="sm" onClick={onViewDetail}>
          Ver detalle por sitio
        </Button>
      )}
    </div>
  );
}
