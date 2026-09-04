/**
 * GrowthCurveSection — contenedor de la curva de crecimiento (feature 040,
 * US3, T051): compone `PercentileToolbar` + (`PercentileChart` |
 * `PercentileTable`) + `PercentileInterpretationBlock` + la nota de
 * maduración del indicador activo, per `contracts/growth-tab-ui.md`
 * §Component tree. Reemplaza el slot temporal de `GrowthCharts.tsx` en
 * `GrowthTab.tsx` (T052).
 *
 * Dueño de todo el estado de la vista (`indicator`/`axis`/`range`/`detail`/
 * `view`) y de la exportación PNG — sus hijos (`PercentileToolbar`,
 * `PercentileChart`, `PercentileTable`) son puramente controlados.
 *
 * Modo padre (T059, US4, `contracts/growth-tab-ui.md`): `PercentileChart`
 * recibe `preset="family"` (línea del atleta + P50 + banda P3–P97
 * únicamente, sin marcador PHV/PWV, per el propio componente) y
 * `PercentileInterpretationBlock` recibe `hideAdvanced`. El eje biológico ya
 * estaba oculto para padres (`showAxisToggle`); el botón "Detalle" se oculta
 * con `PercentileToolbar.showDetailToggle={false}` (prop nueva y opcional,
 * per `GrowthTab.parent.test.tsx` "no ofrece el botón 'Detalle'" — el
 * control no tiene sentido en `preset="family"`, que ya ignora `detail`).
 *
 * El toggle "Tabla" sí sigue visible (el contrato no exige ocultarlo), pero
 * la vista efectiva queda fija en "Gráfica" para una familia: `PercentileTable.tsx`
 * aún no tiene una variante segura para ese público (muestra Z-score,
 * percentil y la etiqueta clínica del coach sin filtrar — violaría FR-016
 * "MUST NOT show Z-scores, percentiles … clinical headline labels"). Darle
 * una variante familiar a esa tabla es trabajo de otra tarea; acá basta con
 * no montarla nunca en modo padre.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { PercentileChart } from "@/components/athletes/growth/PercentileChart";
import { PercentileTable } from "@/components/athletes/growth/PercentileTable";
import {
  PercentileToolbar,
  type GrowthChartAxis,
  type GrowthChartRange,
  type GrowthChartView,
  type PercentileToolbarIndicatorOption,
} from "@/components/athletes/growth/PercentileToolbar";
import { PercentileInterpretationBlock } from "@/components/athletes/PercentileInterpretationBlock";
import type { GrowthIndicator } from "@/lib/growth/lms";
import { useAuthStore } from "@/store/auth.store";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { UserRole } from "@/types/enums";

export interface GrowthCurveSectionProps {
  athlete: AthleteDetailOut;
  records: AnthropometricRecord[];
  mode: "coach" | "parent";
}

const INDICATOR_OPTIONS: PercentileToolbarIndicatorOption[] = [
  { key: "height_for_age", label: "Talla" },
  { key: "bmi_for_age", label: "IMC" },
  { key: "weight_for_age", label: "Peso" },
];

// Notas de pie por indicador — aclaran el significado clínico de la línea
// vertical de maduración (PHV/PWV) para evitar lecturas erróneas (p. ej.
// interpretar la subida de IMC peri-PHV como adiposidad cuando refleja masa
// magra). Duplicadas a propósito de `PercentileCurves.tsx` (eliminado en
// T052): ese componente además usaba este texto en un popover junto al
// título del eje Y dentro del propio `PercentileChart.tsx` (T050); esta
// copia es la nota persistente que se ve tanto en vista gráfica como tabla.
const INDICATOR_PHV_NOTES: Record<GrowthIndicator, string> = {
  height_for_age: "Línea PHV: edad estimada del pico de velocidad de talla (Mirwald).",
  bmi_for_age:
    "Subida del IMC alrededor del PHV refleja aumento de masa magra, no adiposidad.",
  weight_for_age:
    "Pico de velocidad de peso (PWV) coincide con PHV en hombres y se retrasa ~6 meses en mujeres.",
};

/** Registro con la fecha de evaluación más reciente, o `null` sin registros. */
function findLatestRecord(records: AnthropometricRecord[]): AnthropometricRecord | null {
  if (records.length === 0) return null;
  return [...records].sort(
    (a, b) => new Date(b.evaluation_date).getTime() - new Date(a.evaluation_date).getTime(),
  )[0];
}

export function GrowthCurveSection({ athlete, records, mode }: GrowthCurveSectionProps) {
  const isFamily = mode === "parent";
  const role = useAuthStore((state) => state.user?.role);
  const isCoachRole = role === UserRole.coach || role === UserRole.admin;

  // OMS no publica weight_for_age para mayores de 10 años (mismo criterio
  // que el `GrowthCharts.tsx` que este componente reemplaza).
  const showWeight = athlete.age_decimal == null || athlete.age_decimal <= 10;
  const indicatorOptions = useMemo(
    () => INDICATOR_OPTIONS.filter((option) => option.key !== "weight_for_age" || showWeight),
    [showWeight],
  );

  const [indicator, setIndicator] = useState<GrowthIndicator>("height_for_age");
  // Si weight_for_age deja de estar disponible (p. ej. el atleta cumplió
  // años), cae a talla en vez de quedar en un indicador sin toggle visible.
  const safeIndicator: GrowthIndicator =
    indicator === "weight_for_age" && !showWeight ? "height_for_age" : indicator;

  const [axis, setAxis] = useState<GrowthChartAxis>("chrono");
  const [range, setRange] = useState<GrowthChartRange>("window");
  const [detail, setDetail] = useState(false);
  const [view, setView] = useState<GrowthChartView>("chart");
  const [isExporting, setIsExporting] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  const latestRecord = useMemo(() => findLatestRecord(records), [records]);
  const phvAgeMonths =
    latestRecord?.age_at_phv != null ? latestRecord.age_at_phv * 12 : undefined;

  // El eje biológico sólo aplica en modo coach, para un usuario autenticado
  // con rol coach/admin, con PHV conocido y nunca para IMC (data-model.md
  // §7: "axis resets to chrono when indicator === bmi_for_age ... or mode
  // === parent"). Se exige `mode === "coach"` Y el rol real porque un padre
  // no debería ver el eje biológico aunque, por error, se le montara la
  // vista de coach.
  const showAxisToggle =
    mode === "coach" &&
    isCoachRole &&
    safeIndicator !== "bmi_for_age" &&
    phvAgeMonths !== undefined;

  useEffect(() => {
    if (!showAxisToggle && axis !== "chrono") {
      setAxis("chrono");
    }
  }, [showAxisToggle, axis]);

  async function handleExportPng() {
    if (!exportRef.current || isExporting) return;
    setIsExporting(true);
    try {
      const { toPng } = await import("html-to-image");
      const dataUrl = await toPng(exportRef.current, {
        cacheBust: true,
        // Token de superficie en vez de un hex literal (constitution III /
        // contrato de tokens) — siempre resuelve a blanco en modo claro,
        // que es el fondo esperado para compartir/imprimir la gráfica.
        backgroundColor: "var(--color-surface)",
        pixelRatio: 2,
      });
      const link = document.createElement("a");
      link.download = `crecimiento-${safeIndicator}-${Date.now()}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error("Error exportando gráfica:", err);
    } finally {
      setIsExporting(false);
    }
  }

  // Per contrato — "Curve | ... | < 1 record → not rendered": sin
  // mediciones no hay nada que graficar ni tabular; el estado vacío del
  // bloque resumen (`GrowthTab`/`GrowthSummarySection`) ya cubre este caso.
  if (records.length === 0) return null;

  // Modo padre: la vista queda fija en "Gráfica" (ver docstring del módulo —
  // `PercentileTable.tsx` no es family-safe todavía) y la nota de pie es la
  // que ya arma `PercentileChart` para `preset="family"`, así que la nota de
  // maduración por indicador (coach-only) no aplica.
  const effectiveView: GrowthChartView = isFamily ? "chart" : view;
  const phvNote =
    !isFamily && phvAgeMonths !== undefined ? INDICATOR_PHV_NOTES[safeIndicator] : null;

  return (
    <div className="space-y-4" data-testid="growth-curve">
      <PercentileToolbar
        indicators={indicatorOptions}
        indicator={safeIndicator}
        onIndicator={setIndicator}
        axis={axis}
        onAxis={setAxis}
        showAxisToggle={showAxisToggle}
        range={range}
        onRange={setRange}
        detail={detail}
        onDetail={setDetail}
        showDetailToggle={!isFamily}
        view={effectiveView}
        onView={isFamily ? () => {} : setView}
        onExport={effectiveView === "chart" ? handleExportPng : undefined}
        exporting={isExporting}
      />

      <div ref={exportRef} className="space-y-3">
        {effectiveView === "chart" ? (
          <PercentileChart
            indicator={safeIndicator}
            records={records}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
            phvAgeMonths={phvAgeMonths}
            axis={axis}
            range={range}
            detail={detail}
            preset={isFamily ? "family" : "coach"}
          />
        ) : (
          <PercentileTable
            records={records}
            indicator={safeIndicator}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
          />
        )}

        {latestRecord && (
          <PercentileInterpretationBlock
            record={latestRecord}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
            indicator={safeIndicator}
            hideAdvanced={isFamily}
          />
        )}

        {phvNote && <p className="text-[11px] italic text-mid-gray">{phvNote}</p>}
      </div>
    </div>
  );
}
