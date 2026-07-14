import { AlertTriangle, Bike, Info, Ruler } from "lucide-react";

import type {
  AnthropometricRecord,
  BikeFitCategory,
  MorphologyMetrics,
} from "@/types/anthropometry.types";

interface MorphologyCardProps {
  latestRecord?: AnthropometricRecord;
}

const BIKE_FIT_LABEL: Record<BikeFitCategory, string> = {
  short_reach: "Reach corto",
  standard: "Estándar",
  long_reach: "Reach largo",
};

const BIKE_FIT_BADGE: Record<BikeFitCategory, string> = {
  short_reach: "bg-blue-100 text-blue-800",
  standard: "bg-light-gray text-charcoal",
  long_reach: "bg-purple-100 text-purple-800",
};

function formatDelta(delta: number): string {
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)} cm`;
}

interface InfoBlockProps {
  morphology: MorphologyMetrics;
  armSpanCm: number;
  standingHeightCm: number;
}

function MorphologyContent({ morphology, armSpanCm, standingHeightCm }: InfoBlockProps) {
  return (
    <div className="space-y-4">
      {/* Métricas base */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg bg-light-gray p-3">
          <p className="text-xs uppercase tracking-wide text-mid-gray">Talla</p>
          <p className="mt-1 text-lg font-semibold text-charcoal">
            {standingHeightCm.toFixed(1)} cm
          </p>
        </div>
        <div className="rounded-lg bg-light-gray p-3">
          <p className="text-xs uppercase tracking-wide text-mid-gray">Envergadura</p>
          <p className="mt-1 text-lg font-semibold text-charcoal">
            {armSpanCm.toFixed(1)} cm
          </p>
        </div>
        <div className="rounded-lg bg-light-gray p-3">
          <p className="text-xs uppercase tracking-wide text-mid-gray">Δ talla–enverg.</p>
          <p className="mt-1 text-lg font-semibold text-charcoal">
            {formatDelta(morphology.arm_span_height_delta_cm)}
          </p>
        </div>
        <div className="rounded-lg bg-light-gray p-3">
          <p className="text-xs uppercase tracking-wide text-mid-gray">Ape index</p>
          <p className="mt-1 text-lg font-semibold text-charcoal">
            {morphology.ape_index.toFixed(3)}
          </p>
        </div>
      </div>

      {/* Cribado postural */}
      {morphology.posture_screening_flag && morphology.posture_screening_message && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{morphology.posture_screening_message}</span>
        </div>
      )}

      {/* Bike fit */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <Bike size={16} className="text-mid-gray" />
          <span className="text-sm font-medium text-charcoal">Ajuste de bici sugerido</span>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              BIKE_FIT_BADGE[morphology.bike_fit_category]
            }`}
          >
            {BIKE_FIT_LABEL[morphology.bike_fit_category]}
          </span>
        </div>
        <p className="text-sm text-mid-gray">{morphology.bike_fit_guidance}</p>
      </div>

      {/* Advisory ape index inestable */}
      {morphology.ape_index_advisory && (
        <div
          role="note"
          className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900"
        >
          <Info size={14} className="mt-0.5 shrink-0" />
          <span>{morphology.ape_index_advisory}</span>
        </div>
      )}

      <p
        className="text-xs text-mid-gray pt-3"
        style={{ borderTop: "1px solid rgba(34, 42, 53, 0.08)" }}
      >
        Datos orientativos. No utilizar para selección de talento. Re-evaluar cada
        3-6 meses durante el crecimiento.
      </p>
    </div>
  );
}

export function MorphologyCard({ latestRecord }: MorphologyCardProps) {
  const showEmpty =
    !latestRecord ||
    latestRecord.arm_span_cm == null ||
    !latestRecord.morphology;

  return (
    <div className="rounded-xl bg-white p-5 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <Ruler size={16} className="text-mid-gray" />
        <h4
          className="font-display text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          Morfología y ajuste de bici
        </h4>
      </div>

      {showEmpty ? (
        <p className="text-sm text-mid-gray">
          Registra envergadura en la próxima medición para ver el índice ape, la
          comparación talla–envergadura y la guía de ajuste de bici.
        </p>
      ) : (
        <MorphologyContent
          morphology={latestRecord!.morphology!}
          armSpanCm={Number(latestRecord!.arm_span_cm)}
          standingHeightCm={Number(latestRecord!.standing_height_cm)}
        />
      )}
    </div>
  );
}
