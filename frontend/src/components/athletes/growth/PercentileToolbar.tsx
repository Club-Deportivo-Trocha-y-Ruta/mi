/**
 * PercentileToolbar — controles del panel de curvas de crecimiento (feature
 * 040, US3, T049): selector de indicador, eje de edad (coach), ventana de
 * edad visible, tipo de vista (gráfica/tabla), "Detalle" (P10/P25/P75/P90)
 * y exportación PNG — copy exacta de `contracts/growth-tab-ui.md` §Toolbar.
 *
 * Puramente controlado: no guarda estado propio ni decide gating de
 * negocio (qué indicadores están disponibles por edad, si el toggle de eje
 * aplica según rol/indicador, si hay algo que exportar). Ese cálculo vive
 * en `GrowthCurveSection.tsx`, el único llamador — este componente sólo
 * renderiza lo que recibe.
 *
 * Objetivos táctiles ≥ 48 px (constitution III / contrato §Accesibilidad):
 * `ToggleGroupItem` trae `h-9`/`h-10` por defecto en `components/ui/toggle.tsx`,
 * así que se sobreescribe a `min-h-12`; los `Button` usan `size="lg"`
 * (`min-h-12` nativo de `components/ui/button.tsx`).
 */
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { GrowthIndicator } from "@/lib/growth/lms";

export type GrowthChartAxis = "chrono" | "bio";
export type GrowthChartRange = "window" | "full";
export type GrowthChartView = "chart" | "table";

export interface PercentileToolbarIndicatorOption {
  key: GrowthIndicator;
  label: string;
}

export interface PercentileToolbarProps {
  indicators: PercentileToolbarIndicatorOption[];
  indicator: GrowthIndicator;
  onIndicator: (indicator: GrowthIndicator) => void;
  axis: GrowthChartAxis;
  onAxis: (axis: GrowthChartAxis) => void;
  /**
   * El toggle de eje sólo aplica para coach/admin y nunca para IMC
   * (`data-model.md` §7 — "axis resets to chrono when indicator ===
   * bmi_for_age ... or mode === parent"); el llamador ya resuelve esa
   * condición contra `useAuthStore` y el indicador activo.
   */
  showAxisToggle: boolean;
  range: GrowthChartRange;
  onRange: (range: GrowthChartRange) => void;
  detail: boolean;
  onDetail: (detail: boolean) => void;
  /**
   * El botón "Detalle" (P10/P25/P75/P90) no aplica a la vista familiar
   * (feature 040, US4, T059 — `preset="family"` de `PercentileChart` ya
   * ignora `detail`; `GrowthCurveSection` pasa `false` en modo padre para
   * que el control ni siquiera aparezca, per `GrowthTab.parent.test.tsx`
   * "no ofrece el botón 'Detalle'"). Opcional y por defecto `true` para no
   * afectar a ningún llamador existente.
   */
  showDetailToggle?: boolean;
  view: GrowthChartView;
  onView: (view: GrowthChartView) => void;
  /** Ausente = sin botón de exportar (p. ej. vista tabla, o sin registros). */
  onExport?: () => void;
  exporting?: boolean;
}

const TOGGLE_ITEM_CLASSES =
  "min-h-12 rounded-lg border border-border-gray px-3 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white";

export function PercentileToolbar({
  indicators,
  indicator,
  onIndicator,
  axis,
  onAxis,
  showAxisToggle,
  range,
  onRange,
  detail,
  onDetail,
  showDetailToggle = true,
  view,
  onView,
  onExport,
  exporting = false,
}: PercentileToolbarProps) {
  return (
    <div
      data-testid="growth-curve-toolbar"
      className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
    >
      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          value={indicator}
          onValueChange={(value) => {
            if (value) onIndicator(value as GrowthIndicator);
          }}
          aria-label="Indicador de crecimiento"
          className="flex flex-wrap gap-1.5"
        >
          {indicators.map((option) => (
            <ToggleGroupItem key={option.key} value={option.key} className={TOGGLE_ITEM_CLASSES}>
              {option.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        {showAxisToggle && (
          <ToggleGroup
            type="single"
            value={axis}
            onValueChange={(value) => {
              if (value) onAxis(value as GrowthChartAxis);
            }}
            aria-label="Eje de edad"
            className="flex flex-wrap gap-1.5"
          >
            <ToggleGroupItem value="chrono" className={TOGGLE_ITEM_CLASSES}>
              Cronológica
            </ToggleGroupItem>
            <ToggleGroupItem value="bio" className={TOGGLE_ITEM_CLASSES}>
              Biológica
            </ToggleGroupItem>
          </ToggleGroup>
        )}

        <ToggleGroup
          type="single"
          value={range}
          onValueChange={(value) => {
            if (value) onRange(value as GrowthChartRange);
          }}
          aria-label="Rango de edad visible"
          className="flex flex-wrap gap-1.5"
        >
          <ToggleGroupItem value="full" className={TOGGLE_ITEM_CLASSES}>
            Ver 5–19 años
          </ToggleGroupItem>
          <ToggleGroupItem value="window" className={TOGGLE_ITEM_CLASSES}>
            Ver alrededor de las mediciones
          </ToggleGroupItem>
        </ToggleGroup>

        {showDetailToggle && (
          <Button
            type="button"
            variant={detail ? "default" : "outline"}
            size="lg"
            aria-pressed={detail}
            onClick={() => onDetail(!detail)}
          >
            Detalle
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          value={view}
          onValueChange={(value) => {
            if (value) onView(value as GrowthChartView);
          }}
          aria-label="Vista"
          className="flex flex-wrap gap-1.5"
        >
          <ToggleGroupItem value="chart" className={TOGGLE_ITEM_CLASSES}>
            Gráfica
          </ToggleGroupItem>
          <ToggleGroupItem value="table" className={TOGGLE_ITEM_CLASSES}>
            Tabla
          </ToggleGroupItem>
        </ToggleGroup>

        {onExport && (
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={onExport}
            disabled={exporting}
            data-testid="export-png-button"
          >
            <Download className="size-4" aria-hidden="true" />
            {exporting ? "Exportando…" : "Descargar PNG"}
          </Button>
        )}
      </div>
    </div>
  );
}
