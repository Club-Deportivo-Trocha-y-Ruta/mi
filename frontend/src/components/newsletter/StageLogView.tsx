/**
 * StageLogView — renderizador compartido de la bitácora de etapa
 * (feature 038, T301). Un único componente para las tres superficies
 * (web padre, preview del estudio del coach, base del email/PDF v2):
 * recibe un `StageLog` (o su vista de padre, `ParentStageLog`) y pinta
 * los bloques en el orden fijo de AC-1.1.
 *
 * CRÍTICO (AC-1.1 / AC-1.4): un bloque sin datos NUNCA se renderiza como
 * placeholder tipo "sin información" — si el campo es `null` o una lista
 * vacía, ese bloque simplemente no aparece. Esto es cierto para AMBOS
 * modos (no solo `mode="parent"`): el estudio del coach previsualiza
 * exactamente lo que ve la familia; los estados "Vacío"/"Oculto" propios
 * del coach viven en el panel de bloques del estudio (T302), no aquí.
 *
 * Cada bloque raíz lleva `data-block="<nombre>"` para que el estudio del
 * coach pueda hacer scroll-to (mismos anchors que usará `BlockCard`).
 *
 * `mode` solo cambia una cosa en este componente: la procedencia del
 * insight adjunto (`analyst_reading.source_insight_id`) se muestra
 * únicamente en `mode="coach"` — el DTO de padres nunca la incluye
 * (`to_parent_dto`, data-model.md §1), así que en `mode="parent"` no hay
 * nada que ocultar (el campo no llega).
 */
import { AnalystReading } from "./AnalystReading";
import { BadgesRow } from "./BadgesRow";
import { CoachNote } from "./CoachNote";
import { EffortProfile } from "./EffortProfile";
import { FamilyCompass } from "./FamilyCompass";
import { NextSegment } from "./NextSegment";
import { ObservationsList } from "./ObservationsList";
import { PhotosGrid } from "./PhotosGrid";
import { StageHeader } from "./StageHeader";
import { SummitCard } from "./SummitCard";
import { TrailRoute } from "./TrailRoute";
import type { ParentStageLog, StageLog } from "@/types/stageLog.types";

export interface StageLogViewProps {
  stageLog: StageLog | ParentStageLog;
  mode: "coach" | "parent";
}

function hasSourceInsightId(
  analystReading: NonNullable<(StageLog | ParentStageLog)["analyst_reading"]>,
): analystReading is StageLog["analyst_reading"] & { source_insight_id: number } {
  return "source_insight_id" in analystReading;
}

export function StageLogView({ stageLog, mode }: StageLogViewProps) {
  return (
    <div
      data-surface="bitacora"
      data-mode={mode}
      className="stage-log-view space-y-5"
      data-testid="stage-log-view"
    >
      <div data-block="header">
        <StageHeader
          stageNumber={stageLog.stage_number}
          periodLabel={stageLog.period_label}
          isCurrentMonth={stageLog.is_current_month}
          stageTitle={stageLog.stage_title}
        />
      </div>

      {stageLog.trail.length > 0 && (
        <div data-block="trail">
          <TrailRoute
            waypoints={stageLog.trail}
            summitDate={stageLog.summit?.date ?? null}
          />
        </div>
      )}

      {stageLog.summit && (
        <div data-block="summit">
          <SummitCard summit={stageLog.summit} />
        </div>
      )}

      {stageLog.observations.length > 0 && (
        <div data-block="observations">
          <ObservationsList observations={stageLog.observations} />
        </div>
      )}

      {stageLog.analyst_reading && (
        <div data-block="analyst-reading">
          <AnalystReading
            analystReading={stageLog.analyst_reading}
            mode={mode}
            sourceInsightId={
              hasSourceInsightId(stageLog.analyst_reading)
                ? stageLog.analyst_reading.source_insight_id
                : undefined
            }
          />
        </div>
      )}

      {stageLog.effort_profile.length > 0 && (
        <div data-block="effort-profile">
          <EffortProfile weeks={stageLog.effort_profile} />
        </div>
      )}

      {stageLog.next_segment && (
        <div data-block="next-segment">
          <NextSegment nextSegment={stageLog.next_segment} />
        </div>
      )}

      {stageLog.family_compass && (
        <div data-block="family-compass">
          <FamilyCompass compass={stageLog.family_compass} />
        </div>
      )}

      {stageLog.badges.length > 0 && (
        <div data-block="badges">
          <BadgesRow badges={stageLog.badges} />
        </div>
      )}

      {stageLog.photos.length > 0 && (
        <div data-block="photos">
          <PhotosGrid photos={stageLog.photos} />
        </div>
      )}

      {stageLog.coach_note && (
        <div data-block="coach-note">
          <CoachNote note={stageLog.coach_note} />
        </div>
      )}
    </div>
  );
}
