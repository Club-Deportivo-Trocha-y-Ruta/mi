/**
 * GrowthTab — contenedor mode-aware del tab "Crecimiento" (feature 040, US2,
 * T041), per `contracts/growth-tab-ui.md`. Se monta con `React.lazy` desde
 * `routes/athletes/AthleteDetailPage.tsx` (T042) para sacar la curva
 * (recharts) del chunk de entrada.
 *
 * Composición modo coach (orden fijo del contrato — T038-T040 ya
 * entregaron `GrowthStatusRow`/`NextMeasurementCard`/`GrowthAlerts` y el
 * `TrainingReadiness` refactorizado; T052 reemplaza el slot temporal de
 * `GrowthCharts` por `GrowthCurveSection`; T068 inserta `MaturationTimeline`
 * justo después de la curva):
 *
 *   GrowthAlerts → GrowthStatusRow → NextMeasurementCard → TrainingReadiness
 *   → GrowthCurveSection → MaturationTimeline → MorphologyCard →
 *   PHVExplanationCard → AnthropometryHistory (compacto) → ResearchReferences.
 *
 * `NutritionalClassification` deja de usarse en modo coach: sus dos
 * clasificaciones (talla/IMC) ahora las muestra `GrowthStatusRow` con datos
 * ya calculados en el servidor (`useGrowthSummary`), sin duplicar el
 * cálculo LMS en el cliente.
 *
 * Composición modo padre (feature 040, US4, T062 — reemplaza la paridad
 * provisional con `MyAthleteDetailPage.tsx` de las fases previas): tarjetas
 * familiares (`FamilyStageCard` → `FamilyBandCards`, sin numerales) →
 * `GrowthCurveSection` (preset familiar) → `PHVExplanationCard` (solo
 * lectura, `audience="family"`) → `AnthropometryHistory` (modo padre). Nada
 * más: sin `GrowthAlerts`/`GrowthStatusRow`/`NextMeasurementCard` (esos
 * tres son el bloque resumen del coach), ni `TrainingReadiness`,
 * `MorphologyCard`, `MaturationTimeline` o `ResearchReferences` (exclusivos
 * del coach per `contracts/growth-tab-ui.md` §Component tree).
 *
 * Datos: `useAnthropometry(athlete.id)` (existente, ya cacheada por la
 * página contenedora — misma query key, sin refetch adicional) +
 * `useGrowthSummary(athlete.id)` (nueva, feature 040): el modo padre solo
 * usa `summary.stage` / `summary.latest_evaluation_date` (tarjeta de etapa)
 * y `summary.latest` (tarjetas de banda) — ambos ya reflejan la medición
 * más reciente calculada en el servidor, así ninguna tarjeta familiar
 * necesita ordenar `records` por fecha ella misma. Cada uno de los demás
 * componentes hijos (`AnthropometryHistory`, `GrowthCurveSection`,
 * `TrainingReadiness`, `MorphologyCard`, `PHVExplanationCard`) sigue
 * gobernando sus propios estados de carga/vacío/error; este componente
 * sólo gestiona el bloque de resumen (coach: `GrowthAlerts`/
 * `GrowthStatusRow`/`NextMeasurementCard`; padre: tarjetas familiares) que
 * depende del endpoint nuevo, per la tabla de estados de
 * `contracts/growth-tab-ui.md` (filas "Status row / next measurement" y
 * "Family cards"). Un error en `growth-summary` no tumba el resto del tab.
 */
import { TrendingUp } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";

import { PHVExplanationCard } from "@/components/ai/PHVExplanationCard";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { FamilyBandCards } from "@/components/athletes/growth/FamilyBandCards";
import { FamilyStageCard } from "@/components/athletes/growth/FamilyStageCard";
import { GrowthAlerts } from "@/components/athletes/growth/GrowthAlerts";
import { GrowthCurveSection } from "@/components/athletes/growth/GrowthCurveSection";
import { GrowthStatusRow } from "@/components/athletes/growth/GrowthStatusRow";
import { MaturationTimeline } from "@/components/athletes/growth/MaturationTimeline";
import { NextMeasurementCard } from "@/components/athletes/growth/NextMeasurementCard";
import { MorphologyCard } from "@/components/athletes/MorphologyCard";
import { ResearchReferences } from "@/components/athletes/ResearchReferences";
import { TrainingReadiness } from "@/components/athletes/TrainingReadiness";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { StatCard } from "@/components/shared/StatCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useGrowthSummary } from "@/hooks/athletes/useGrowthSummary";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { GrowthSummary } from "@/types/growth.types";

export interface GrowthTabProps {
  athlete: AthleteDetailOut;
  mode: "coach" | "parent";
  /**
   * CTA para llevar al coach al formulario de medición — se reenvía tal
   * cual a `PHVExplanationCard.onMeasurementCTA` y al botón del
   * `EmptyState` del bloque resumen. No se usa en modo padre (los padres
   * no registran mediciones).
   */
  onRecordMeasurement?: () => void;
}

// ---------------------------------------------------------------------------
// Bloque resumen (coach) — gobernado por `useGrowthSummary`
// ---------------------------------------------------------------------------

/** Placeholder de carga del bloque resumen — misma forma que `GrowthStatusRow` + `NextMeasurementCard`. */
function GrowthSummarySkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando resumen de crecimiento…"
      className="space-y-3"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Etapa" value="" isLoading />
        <StatCard label="Velocidad de talla" value="" isLoading />
        <StatCard label="Talla para la edad" value="" isLoading />
        <StatCard label="IMC para la edad" value="" isLoading />
      </div>
      <Skeleton className="h-12 w-full rounded-xl" />
    </div>
  );
}

interface GrowthSummarySectionProps {
  summaryQuery: UseQueryResult<GrowthSummary, Error>;
  records: AnthropometricRecord[];
  onRecordMeasurement?: () => void;
}

function GrowthSummarySection({
  summaryQuery,
  records,
  onRecordMeasurement,
}: GrowthSummarySectionProps) {
  if (summaryQuery.isLoading) {
    return <GrowthSummarySkeleton />;
  }

  if (summaryQuery.isError) {
    return (
      <ErrorState
        message="No se pudo cargar el resumen de crecimiento."
        onRetry={() => {
          void summaryQuery.refetch();
        }}
      />
    );
  }

  const summary = summaryQuery.data;

  if (!summary || summary.records_count === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="Registra la primera medición"
        description="La etapa, la velocidad de talla y la próxima medición aparecen aquí en cuanto haya al menos un registro antropométrico."
        action={
          onRecordMeasurement && (
            <Button type="button" size="lg" onClick={onRecordMeasurement}>
              Registrar medición
            </Button>
          )
        }
      />
    );
  }

  return (
    <>
      <GrowthAlerts alerts={summary.alerts} />
      <GrowthStatusRow summary={summary} records={records} />
      <NextMeasurementCard measurement={summary.measurement} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Modo coach
// ---------------------------------------------------------------------------

interface ModeProps {
  athlete: AthleteDetailOut;
  records: AnthropometricRecord[];
  anthropometryQuery: UseQueryResult<AnthropometricRecord[], Error>;
  latestRecord: AnthropometricRecord | undefined;
  onRecordMeasurement?: () => void;
}

function CoachGrowthTab({
  athlete,
  records,
  anthropometryQuery,
  latestRecord,
  onRecordMeasurement,
}: ModeProps) {
  const summaryQuery = useGrowthSummary(athlete.id);

  return (
    <div className="space-y-5">
      <GrowthSummarySection
        summaryQuery={summaryQuery}
        records={records}
        onRecordMeasurement={onRecordMeasurement}
      />

      <TrainingReadiness
        athlete={athlete}
        latestRecord={latestRecord}
        alerts={summaryQuery.data?.alerts}
      />

      <div className="rounded-xl bg-white p-5 shadow-card">
        <GrowthCurveSection athlete={athlete} records={records} mode="coach" />
      </div>

      <MaturationTimeline
        stage={summaryQuery.data?.stage ?? null}
        maturityOffset={summaryQuery.data?.maturity_offset ?? null}
        ageAtPhv={summaryQuery.data?.age_at_phv ?? null}
      />

      <MorphologyCard latestRecord={latestRecord} />

      <PHVExplanationCard
        athleteId={athlete.id}
        hasRecords={records.length > 0}
        onMeasurementCTA={onRecordMeasurement}
        audience="coach"
      />

      <div className="rounded-xl bg-white p-5 shadow-card">
        <AnthropometryHistory
          records={records}
          isLoading={anthropometryQuery.isLoading}
          athleteId={athlete.id}
          mode="coach"
        />
      </div>

      <ResearchReferences />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modo padre (feature 040, US4, T062) — tarjetas familiares narrativas.
// ---------------------------------------------------------------------------

/** Skeleton del bloque de tarjetas familiares mientras carga `useGrowthSummary`. */
function FamilyCardsSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando etapa de desarrollo…"
      className="space-y-3"
    >
      <Skeleton className="h-20 w-full rounded-xl" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </div>
    </div>
  );
}

interface FamilyCardsSectionProps {
  summaryQuery: UseQueryResult<GrowthSummary, Error>;
  sex: AthleteDetailOut["sex"];
}

/** `FamilyStageCard` → `FamilyBandCards`, gobernadas por `useGrowthSummary`
 *  (fila "Family cards" de la tabla de estados de `contracts/growth-tab-ui.md`). */
function FamilyCardsSection({ summaryQuery, sex }: FamilyCardsSectionProps) {
  if (summaryQuery.isLoading) {
    return <FamilyCardsSkeleton />;
  }

  if (summaryQuery.isError) {
    return (
      <ErrorState
        message="No se pudo cargar el crecimiento."
        onRetry={() => {
          void summaryQuery.refetch();
        }}
      />
    );
  }

  const summary = summaryQuery.data;

  if (!summary || summary.records_count === 0) {
    return <EmptyState icon={TrendingUp} title="Aún no hay mediciones" />;
  }

  return (
    <>
      <FamilyStageCard
        stage={summary.stage}
        latestEvaluationDate={summary.latest_evaluation_date}
        sex={sex}
      />
      <FamilyBandCards latest={summary.latest} />
    </>
  );
}

/**
 * Orden fijo del contrato (`contracts/growth-tab-ui.md` §Component tree,
 * también resumido en el docstring del módulo): tarjetas familiares → curva
 * familiar → IA de solo lectura → historial. Nada de `GrowthAlerts`/
 * `GrowthStatusRow`/`NextMeasurementCard` (bloque resumen exclusivo del
 * coach) ni de `TrainingReadiness`/`MorphologyCard`/`ResearchReferences`.
 */
function ParentGrowthTab({ athlete, records, anthropometryQuery }: ModeProps) {
  const summaryQuery = useGrowthSummary(athlete.id);

  return (
    <div className="space-y-5">
      <FamilyCardsSection summaryQuery={summaryQuery} sex={athlete.sex} />

      <div className="rounded-xl bg-white p-5 shadow-card">
        <GrowthCurveSection athlete={athlete} records={records} mode="parent" />
      </div>

      <PHVExplanationCard
        athleteId={athlete.id}
        hasRecords={records.length > 0}
        readOnly
        audience="family"
      />

      <div className="rounded-xl bg-white p-5 shadow-card">
        <AnthropometryHistory
          records={records}
          isLoading={anthropometryQuery.isLoading}
          athleteId={athlete.id}
          mode="parent"
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Entrada pública
// ---------------------------------------------------------------------------

export function GrowthTab({ athlete, mode, onRecordMeasurement }: GrowthTabProps) {
  const anthropometryQuery = useAnthropometry(athlete.id);
  const records = anthropometryQuery.data ?? [];
  // API devuelve registros ordenados desc (más reciente primero) — mismo
  // criterio que `AthleteDetailPage.tsx`/`MyAthleteDetailPage.tsx`.
  const latestRecord = records[0];

  const modeProps: ModeProps = {
    athlete,
    records,
    anthropometryQuery,
    latestRecord,
    onRecordMeasurement,
  };

  return (
    <div data-testid="growth-tab">
      {mode === "parent" ? (
        <ParentGrowthTab {...modeProps} />
      ) : (
        <CoachGrowthTab {...modeProps} />
      )}
    </div>
  );
}
