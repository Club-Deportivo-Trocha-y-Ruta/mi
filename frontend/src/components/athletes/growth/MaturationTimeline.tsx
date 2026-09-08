/**
 * MaturationTimeline — línea de tiempo Pre/Circa/Post-PHV con marcador de
 * "hoy" (feature 040, US5, T068), per `contracts/growth-tab-ui.md`
 * (§Component tree: exclusivo modo coach, entre `GrowthCurveSection` y
 * `MorphologyCard`; §Copy: "Pre-PHV", "Estirón (Circa-PHV)", "Post-PHV",
 * caption "Offset {±x.x} · PHV estimado a los {age} años"; §Test ids:
 * `growth-timeline`).
 *
 * CSS puro (sin Recharts, mismo criterio que `Sparkline.tsx`): es una
 * lectura de posición sobre tres bandas fijas, no una gráfica de series —
 * no justifica el costo del chunk de Recharts.
 *
 * El marcador de "hoy" ubica `maturity_offset` (años respecto al PHV
 * estimado, fórmula Mirwald — `lib/phv.ts`) en una barra con dominio fijo
 * [-3, +3] años, recortado (clamp) en los extremos. Los tres tercios
 * iguales de la barra son exactamente los cortes que usa `calculatePHV`
 * para derivar `stage` (offset < -1 → Pre, -1..1 → Circa, > 1 → Post), así
 * el marcador siempre cae dentro del tercio que coincide con la etapa
 * reportada por el servidor.
 *
 * La etapa activa se resalta con el único acento de marca del sistema de
 * diseño (nunca un color propio por etapa — ese mapa Pre=azul/Circa=ámbar/
 * Post=verde se retira de `TrainingReadiness`/`PHVBadge` en T069, per
 * `contracts/growth-tab-ui.md` §Removed) y el color nunca es el único
 * canal: el rótulo pasa a semibold y el marcador + caption repiten la
 * misma información en texto.
 */
import { cn } from "@/lib/utils";
import { MaturationStatus } from "@/types/enums";

export interface MaturationTimelineProps {
  /** Etapa vigente (última medición) — `null` cuando aún no hay registros. */
  stage: MaturationStatus | null;
  /** Años respecto al PHV estimado (fórmula Mirwald) — `null` sin registros. */
  maturityOffset: number | null;
  /** Edad estimada (años) a la que el deportista alcanza el PHV — `null` sin registros. */
  ageAtPhv: number | null;
}

/** Dominio fijo de la barra, en años respecto al PHV — ver docstring del módulo. */
const DOMAIN_MIN_YEARS = -3;
const DOMAIN_MAX_YEARS = 3;

interface StageSegment {
  status: MaturationStatus;
  label: string;
}

const STAGE_SEGMENTS: StageSegment[] = [
  { status: MaturationStatus.PrePHV, label: "Pre-PHV" },
  { status: MaturationStatus.CircaPHV, label: "Estirón (Circa-PHV)" },
  { status: MaturationStatus.PostPHV, label: "Post-PHV" },
];

function clampOffset(offset: number): number {
  return Math.min(DOMAIN_MAX_YEARS, Math.max(DOMAIN_MIN_YEARS, offset));
}

/** Posición horizontal (0-100) del offset recortado dentro del dominio [-3, +3] años. */
function offsetToPercent(offset: number): number {
  const clamped = clampOffset(offset);
  return ((clamped - DOMAIN_MIN_YEARS) / (DOMAIN_MAX_YEARS - DOMAIN_MIN_YEARS)) * 100;
}

/** "+1.2" / "-0.5" / "+0.0" — siempre con signo explícito, un decimal. */
function formatSignedOffset(offset: number): string {
  const sign = offset >= 0 ? "+" : "";
  return `${sign}${offset.toFixed(1)}`;
}

/** Caption fijo del contrato: "Offset {±x.x} · PHV estimado a los {age} años". */
function buildCaption(maturityOffset: number | null, ageAtPhv: number | null): string {
  if (maturityOffset === null || ageAtPhv === null) {
    return "Se necesitan más mediciones para ubicar el PHV en la línea de tiempo.";
  }
  return `Offset ${formatSignedOffset(maturityOffset)} · PHV estimado a los ${ageAtPhv} años`;
}

/** Alternativa textual completa (contrato §Accessibility) — nunca sólo la barra/el trazo. */
function buildAriaLabel(
  stage: MaturationStatus | null,
  maturityOffset: number | null,
  ageAtPhv: number | null,
): string {
  if (stage === null || maturityOffset === null || ageAtPhv === null) {
    return (
      "Línea de tiempo de maduración Pre-PHV, Circa-PHV y Post-PHV: aún no hay " +
      "mediciones suficientes para ubicar al deportista."
    );
  }
  return (
    `Línea de tiempo de maduración Pre-PHV, Circa-PHV y Post-PHV: el deportista está ` +
    `hoy en etapa ${stage}, con un offset de ${formatSignedOffset(maturityOffset)} años ` +
    `respecto al PHV, estimado a los ${ageAtPhv} años.`
  );
}

export function MaturationTimeline({
  stage,
  maturityOffset,
  ageAtPhv,
}: MaturationTimelineProps) {
  const hasMarker = stage !== null && maturityOffset !== null;
  const markerPercent = hasMarker ? offsetToPercent(maturityOffset as number) : null;

  return (
    <div className="rounded-xl bg-white p-5 shadow-card" data-testid="growth-timeline">
      <h4 className="font-display mb-3 text-sm text-charcoal" style={{ letterSpacing: "0.2px" }}>
        Línea de tiempo de maduración
      </h4>

      <div
        role="img"
        aria-label={buildAriaLabel(stage, maturityOffset, ageAtPhv)}
        className="relative pt-5"
      >
        <div className="flex h-8 overflow-hidden rounded-full border border-border-gray">
          {STAGE_SEGMENTS.map(({ status, label }, index) => {
            const isActive = status === stage;
            return (
              <div
                key={status}
                aria-hidden="true"
                data-stage={status}
                data-active={isActive}
                className={cn(
                  "flex flex-1 items-center justify-center px-1 text-center text-[11px] leading-tight",
                  isActive ? "bg-primary/15 font-semibold text-primary" : "bg-light-gray text-mid-gray",
                  index < STAGE_SEGMENTS.length - 1 && "border-r border-border-gray",
                )}
              >
                {label}
              </div>
            );
          })}
        </div>

        {hasMarker && markerPercent !== null && (
          <div
            aria-hidden="true"
            data-testid="growth-timeline-marker"
            className="absolute top-0 flex -translate-x-1/2 flex-col items-center"
            style={{ left: `${markerPercent}%` }}
          >
            <span className="whitespace-nowrap text-[10px] font-semibold text-charcoal">Hoy</span>
            <div className="h-8 w-0.5 bg-charcoal" />
          </div>
        )}
      </div>

      <p className="mt-2 text-xs text-mid-gray">{buildCaption(maturityOffset, ageAtPhv)}</p>
    </div>
  );
}
