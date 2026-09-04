/**
 * Tests — PercentileToolbar (feature 040, T047/US3).
 *
 * Controles de `GrowthCurveSection` per
 * `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`: indicador
 * (`ToggleGroup`), eje cronológico/biológico (`ToggleGroup`, solo coach),
 * rango (`ToggleGroup`), vista gráfica/tabla (`ToggleGroup`) y dos botones
 * (`Detalle`, `Descargar PNG`). El componente es puramente controlado — no
 * decide qué mostrar por sí mismo (esa lógica de edad/rol vive en
 * `GrowthCurveSection`), así que estos tests solo verifican que refleja las
 * props recibidas y dispara los callbacks correctos.
 *
 * Convención de queries: igual que `RubricSliders.test.tsx` — los
 * `ToggleGroup` de shadcn/radix exponen `role="group"` en la raíz y
 * `role="radio"` en cada item (type="single").
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PercentileToolbar } from "@/components/athletes/growth/PercentileToolbar";
import type { GrowthIndicator } from "@/lib/growth/lms";

const INDICATORS: { key: GrowthIndicator; label: string }[] = [
  { key: "height_for_age", label: "Talla" },
  { key: "bmi_for_age", label: "IMC" },
  { key: "weight_for_age", label: "Peso" },
];

interface RenderOverrides {
  indicators?: { key: GrowthIndicator; label: string }[];
  indicator?: GrowthIndicator;
  onIndicator?: (key: GrowthIndicator) => void;
  axis?: "chrono" | "bio";
  onAxis?: (axis: "chrono" | "bio") => void;
  showAxisToggle?: boolean;
  range?: "window" | "full";
  onRange?: (range: "window" | "full") => void;
  detail?: boolean;
  onDetail?: (detail: boolean) => void;
  view?: "chart" | "table";
  onView?: (view: "chart" | "table") => void;
  onExport?: () => void;
  exporting?: boolean;
}

function renderToolbar(overrides: RenderOverrides = {}) {
  const onIndicator = overrides.onIndicator ?? vi.fn();
  const onAxis = overrides.onAxis ?? vi.fn();
  const onRange = overrides.onRange ?? vi.fn();
  const onDetail = overrides.onDetail ?? vi.fn();
  const onView = overrides.onView ?? vi.fn();

  render(
    <PercentileToolbar
      indicators={overrides.indicators ?? INDICATORS}
      indicator={overrides.indicator ?? "height_for_age"}
      onIndicator={onIndicator}
      axis={overrides.axis ?? "chrono"}
      onAxis={onAxis}
      showAxisToggle={overrides.showAxisToggle ?? true}
      range={overrides.range ?? "window"}
      onRange={onRange}
      detail={overrides.detail ?? false}
      onDetail={onDetail}
      view={overrides.view ?? "chart"}
      onView={onView}
      onExport={overrides.onExport}
      exporting={overrides.exporting}
    />,
  );

  return { onIndicator, onAxis, onRange, onDetail, onView };
}

// ---------------------------------------------------------------------------
// 1. Selector de indicador
// ---------------------------------------------------------------------------

describe("PercentileToolbar — selector de indicador", () => {
  it("renderiza un control por cada entrada de `indicators`, marcando el activo", () => {
    renderToolbar({ indicator: "bmi_for_age" });

    expect(screen.getByRole("radio", { name: "Talla" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByRole("radio", { name: "IMC" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "Peso" })).toBeInTheDocument();
  });

  it("no ofrece Peso cuando `indicators` no lo incluye (filtrado por edad, decidido por el padre)", () => {
    renderToolbar({
      indicators: [
        { key: "height_for_age", label: "Talla" },
        { key: "bmi_for_age", label: "IMC" },
      ],
    });
    expect(screen.queryByRole("radio", { name: "Peso" })).not.toBeInTheDocument();
  });

  it("clic en un indicador dispara onIndicator con la key correcta", async () => {
    const user = userEvent.setup();
    const { onIndicator } = renderToolbar({ indicator: "height_for_age" });

    await user.click(screen.getByRole("radio", { name: "IMC" }));

    expect(onIndicator).toHaveBeenCalledWith("bmi_for_age");
  });
});

// ---------------------------------------------------------------------------
// 2. Eje cronológico/biológico — oculto para IMC y para padres
// ---------------------------------------------------------------------------

describe("PercentileToolbar — eje cronológico/biológico", () => {
  it("con showAxisToggle=false no renderiza ningún control de eje", () => {
    renderToolbar({ showAxisToggle: false });
    expect(screen.queryByRole("radio", { name: "Cronológica" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Biológica" })).not.toBeInTheDocument();
  });

  it("con showAxisToggle=true refleja `axis` y dispara onAxis al hacer clic", async () => {
    const user = userEvent.setup();
    const { onAxis } = renderToolbar({ showAxisToggle: true, axis: "chrono" });

    expect(screen.getByRole("radio", { name: "Cronológica" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "Biológica" })).toHaveAttribute(
      "aria-checked",
      "false",
    );

    await user.click(screen.getByRole("radio", { name: "Biológica" }));
    expect(onAxis).toHaveBeenCalledWith("bio");
  });
});

// ---------------------------------------------------------------------------
// 3. Rango — "Ver 5–19 años" vs "Ver alrededor de las mediciones"
// ---------------------------------------------------------------------------

describe("PercentileToolbar — control de rango", () => {
  it("marca 'Ver alrededor de las mediciones' cuando range='window'", () => {
    renderToolbar({ range: "window" });
    expect(
      screen.getByRole("radio", { name: "Ver alrededor de las mediciones" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Ver 5–19 años" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("clic en 'Ver 5–19 años' dispara onRange('full')", async () => {
    const user = userEvent.setup();
    const { onRange } = renderToolbar({ range: "window" });

    await user.click(screen.getByRole("radio", { name: "Ver 5–19 años" }));
    expect(onRange).toHaveBeenCalledWith("full");
  });
});

// ---------------------------------------------------------------------------
// 4. Detalle — botón toggle P10/P25/P75/P90
// ---------------------------------------------------------------------------

describe("PercentileToolbar — botón Detalle", () => {
  it("refleja `detail` vía aria-pressed y alterna al hacer clic", async () => {
    const user = userEvent.setup();
    const { onDetail } = renderToolbar({ detail: false });

    const button = screen.getByRole("button", { name: "Detalle", pressed: false });
    await user.click(button);

    expect(onDetail).toHaveBeenCalledWith(true);
  });

  it("con detail=true el botón aparece presionado", () => {
    renderToolbar({ detail: true });
    expect(screen.getByRole("button", { name: "Detalle", pressed: true })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 5. Vista — Gráfica / Tabla
// ---------------------------------------------------------------------------

describe("PercentileToolbar — control de vista", () => {
  it("marca 'Gráfica' cuando view='chart' y dispara onView('table') al elegir Tabla", async () => {
    const user = userEvent.setup();
    const { onView } = renderToolbar({ view: "chart" });

    expect(screen.getByRole("radio", { name: "Gráfica" })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    await user.click(screen.getByRole("radio", { name: "Tabla" }));
    expect(onView).toHaveBeenCalledWith("table");
  });
});

// ---------------------------------------------------------------------------
// 6. Exportar PNG
// ---------------------------------------------------------------------------

describe("PercentileToolbar — botón Descargar PNG", () => {
  it("clic en Descargar PNG dispara onExport", async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();
    renderToolbar({ onExport });

    await user.click(screen.getByRole("button", { name: /Descargar PNG/i }));
    expect(onExport).toHaveBeenCalledOnce();
  });

  it("con exporting=true el botón queda deshabilitado", () => {
    renderToolbar({ onExport: vi.fn(), exporting: true });
    expect(screen.getByTestId("export-png-button")).toBeDisabled();
  });
});
