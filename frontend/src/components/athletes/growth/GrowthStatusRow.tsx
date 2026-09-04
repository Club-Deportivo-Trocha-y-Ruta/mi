/**
 * GrowthStatusRow — fila A del tab de crecimiento del coach (feature 040,
 * US2, T038): cuatro tiles de decisión ("Etapa", "Velocidad de talla",
 * "Talla para la edad", "IMC para la edad") sobre `shared/StatCard`, per
 * `contracts/growth-tab-ui.md` (mockup fila A / `docs/18-growth-module-redesign/proposal.md` §5.1).
 *
 * Puramente presentacional: recibe el `GrowthSummary` ya resuelto y los
 * registros antropométricos (para el sparkline de tendencia); no hace
 * fetch ni maneja loading/error — eso es responsabilidad de `GrowthTab`
 * (T041), que sólo monta esta fila cuando la query ya resolvió.
 *
 * D2/"Removed" (`growth-tab-ui.md`): la etapa PHV NUNCA lleva color propio
 * (el viejo mapa Pre=azul/Circa=ámbar/Post=verde de `TrainingReadiness.tsx`
 * se elimina en T040) — `tone`/`badge` sólo se usan en los tiles de banda
 * (talla/IMC), donde el color siempre va acompañado de ícono + etiqueta
 * (Constitution III), y en velocidad cuando hay alerta de crecimiento
 * rápido.
 */
import { StatCard } from "@/components/shared/StatCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Sparkline } from "@/components/athletes/growth/Sparkline";
import { getBandVocabulary } from "@/lib/growth/bands";
import type { AnthropometricRecord, GrowthSource } from "@/types/anthropometry.types";
import type { BandReading, GrowthSummary } from "@/types/growth.types";

export interface GrowthStatusRowProps {
  summary: GrowthSummary;
  records: AnthropometricRecord[];
}

const SPARKLINE_MAX_POINTS = 12;
const DAYS_PER_MONTH = 30.44;

/** Últimas N tallas en orden cronológico ascendente (más reciente al final). */
function heightTrend(records: AnthropometricRecord[]): number[] {
  const chronological = [...records].sort(
    (a, b) => new Date(a.evaluation_date).getTime() - new Date(b.evaluation_date).getTime(),
  );
  return chronological.slice(-SPARKLINE_MAX_POINTS).map((r) => Number(r.standing_height_cm));
}

function formatStageHint(summary: GrowthSummary): string | undefined {
  if (summary.age_at_phv === null || summary.months_from_phv === null) return undefined;
  const months = Math.round(Math.abs(summary.months_from_phv));
  const direction = summary.months_from_phv >= 0 ? `hace ${months} meses` : `en ${months} meses`;
  return `PHV estimado a los ${summary.age_at_phv} años · ${direction}`;
}

function EtapaTile({ summary }: { summary: GrowthSummary }) {
  return (
    <StatCard label="Etapa" value={summary.stage ?? "—"} hint={formatStageHint(summary)} />
  );
}

function VelocidadTile({
  summary,
  records,
}: {
  summary: GrowthSummary;
  records: AnthropometricRecord[];
}) {
  const { velocity, alerts } = summary;
  const trend = heightTrend(records);
  const showSparkline = trend.length >= 2;
  const isRapidGrowth = alerts.includes("rapid_growth");

  if (velocity === null) {
    return <StatCard label="Velocidad de talla" value="—" hint="Se necesitan 2 mediciones" />;
  }

  const windowMonths = Math.round(velocity.window_days / DAYS_PER_MONTH);
  const [expectedMin, expectedMax] = velocity.expected_cm_per_year;
  const hintParts = [
    `últimos ${windowMonths} meses`,
    `esperado ${expectedMin}–${expectedMax} cm/año (orientativo)`,
  ];
  if (velocity.interval_short) hintParts.push("Intervalo corto: valor orientativo");

  return (
    <StatCard
      label="Velocidad de talla"
      value={`${velocity.cm_per_year} cm/año`}
      hint={hintParts.join(" · ")}
      tone={isRapidGrowth ? "warning" : undefined}
      badge={
        <div className="flex flex-col gap-1">
          {isRapidGrowth && <StatusBadge status="warning" label="Crecimiento rápido" />}
          {showSparkline && (
            <Sparkline
              values={trend}
              ariaLabel={`Evolución de talla, últimas ${trend.length} mediciones`}
            />
          )}
        </div>
      }
    />
  );
}

interface BandTileProps {
  label: string;
  indicator: "height_for_age" | "bmi_for_age";
  reading: BandReading | null;
  growthSource: GrowthSource | null;
}

function BandTile({ label, indicator, reading, growthSource }: BandTileProps) {
  if (!reading) {
    return <StatCard label={label} value="—" hint="Sin referencia para la edad" />;
  }

  const vocab = getBandVocabulary(indicator, reading.band);
  const sourceCaption =
    growthSource === "WHO" ? "OMS 2007 · Res. 2465/2016" : "Referencia anterior — pendiente de actualizar";

  return (
    <StatCard
      label={label}
      value={`P${Math.round(reading.percentile)} · Z ${reading.z_score.toFixed(2)}`}
      hint={sourceCaption}
      tone={vocab.tone}
      badge={<StatusBadge status={vocab.tone} label={vocab.coachLabel} />}
    />
  );
}

export function GrowthStatusRow({ summary, records }: GrowthStatusRowProps) {
  return (
    <div
      data-testid="growth-status-row"
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
    >
      <EtapaTile summary={summary} />
      <VelocidadTile summary={summary} records={records} />
      <BandTile
        label="Talla para la edad"
        indicator="height_for_age"
        reading={summary.latest?.height ?? null}
        growthSource={summary.latest?.growth_source ?? null}
      />
      <BandTile
        label="IMC para la edad"
        indicator="bmi_for_age"
        reading={summary.latest?.bmi ?? null}
        growthSource={summary.latest?.growth_source ?? null}
      />
    </div>
  );
}
