/**
 * Tests vitest para WeeklyLoadMeter (feature 031, US3, T046).
 *
 * Cubre el estado de cada medidor de banda (`resolveState` en
 * `WeeklyLoadMeter.tsx`), según la meter state table de
 * `contracts/home-tiles.md`:
 *   - comfortable (<=80% del tope) en ambas bandas → sin copy de advertencia.
 *   - near-cap (>80%, <=100%) en una banda → copy asesor, nunca de alarma.
 *   - over-cap (>100%) en una banda → la barra SIEMPRE renderiza a ancho
 *     completo (100%, nunca recortada/desbordada) + copy con la sobrecarga
 *     en minutos/horas, tono asesor, jamás "¡Exceso!" ni similares.
 *   - esqueleto de carga (`query.isLoading`).
 *
 * Se mockea `useCoachSummary` directamente (mismo patrón que
 * `MeasurementAlerts.test.tsx` mockea `useAlerts`) en vez de pasar por MSW —
 * ya cubierto por `useCoachSummary.test.ts`.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { WeeklyLoadMeter } from "../WeeklyLoadMeter";
import { makeCoachSummary, makeWeeklyLoadBand } from "@/test/msw/dashboardHandlers";
import type { CoachSummary, WeeklyLoadBand } from "@/types/dashboard.types";

vi.mock("@/hooks/dashboard/useCoachSummary", () => ({
  useCoachSummary: vi.fn(),
}));

vi.mock("@/store/trainingFiltersStore", () => ({
  useTrainingFiltersStore: vi.fn((selector: (s: unknown) => unknown) =>
    selector({ setFromDate: vi.fn(), setToDate: vi.fn() }),
  ),
}));

import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";

const mockUseCoachSummary = vi.mocked(useCoachSummary);

function mockSummary(weekly_load: CoachSummary["weekly_load"]) {
  mockUseCoachSummary.mockReturnValue({
    data: makeCoachSummary({ weekly_load }),
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useCoachSummary>);
}

function renderComponent() {
  return render(
    <MemoryRouter>
      <WeeklyLoadMeter />
    </MemoryRouter>,
  );
}

/** Ancho de relleno esperado (mismo cálculo que `MeterBlock`, capado a 100%). */
function expectedFillPct(band: WeeklyLoadBand): number {
  return Math.min((band.planned_minutes / Math.max(band.cap_minutes, 1)) * 100, 100);
}

describe("WeeklyLoadMeter — ambas bandas comfortable", () => {
  it("no muestra copy de advertencia y rellena proporcional al % del tope, en color primary", () => {
    const bands = [
      makeWeeklyLoadBand({ age_band: "10-12", planned_minutes: 240, cap_minutes: 600 }), // 40%
      makeWeeklyLoadBand({ age_band: "13-15", planned_minutes: 300, cap_minutes: 780 }), // ~38.5%
    ];
    mockSummary(bands);

    const { container } = renderComponent();

    expect(screen.getByText("4 h planificadas")).toBeInTheDocument();
    expect(screen.getByText("5 h planificadas")).toBeInTheDocument();

    // Sin copy de estado (ni near-cap ni over-cap) en ninguna de las bandas.
    expect(screen.queryByText(/Cerca del tope/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sobre el tope/)).not.toBeInTheDocument();

    const fills = container.querySelectorAll<HTMLDivElement>(".rounded-full > .rounded-full");
    expect(fills).toHaveLength(2);
    fills.forEach((fill, idx) => {
      expect(fill.style.backgroundColor).toBe("var(--color-primary)");
      expect(fill.style.width).toBe(`${expectedFillPct(bands[idx])}%`);
    });
  });
});

describe("WeeklyLoadMeter — una banda near-cap", () => {
  it('muestra copy asesor "Cerca del tope" en color warning, sin tono de alarma', () => {
    const nearCapBand = makeWeeklyLoadBand({
      age_band: "10-12",
      planned_minutes: 500,
      cap_minutes: 600,
    }); // 83.3% > 80%, <= 100%
    const comfortableBand = makeWeeklyLoadBand({
      age_band: "13-15",
      planned_minutes: 300,
      cap_minutes: 780,
    });
    mockSummary([nearCapBand, comfortableBand]);

    const { container } = renderComponent();

    expect(
      screen.getByText("Cerca del tope — revisa antes de agregar más sesiones."),
    ).toBeInTheDocument();

    // Copy asesor, nunca alarmista.
    expect(screen.queryByText(/¡/)).not.toBeInTheDocument();
    expect(screen.queryByText(/[Ee]xceso/)).not.toBeInTheDocument();

    const fills = container.querySelectorAll<HTMLDivElement>(".rounded-full > .rounded-full");
    expect(fills[0].style.backgroundColor).toBe("var(--color-warning)");
    expect(fills[0].style.width).toBe(`${expectedFillPct(nearCapBand)}%`);

    // La banda comfortable en la misma respuesta sigue sin copy de advertencia.
    expect(screen.queryByText(/sobre el tope/)).not.toBeInTheDocument();
  });
});

describe("WeeklyLoadMeter — una banda over-cap", () => {
  it("renderiza la barra a ancho completo (nunca recortada/desbordada) con copy asesor de la sobrecarga", () => {
    const overCapBand = makeWeeklyLoadBand({
      age_band: "13-15",
      planned_minutes: 810,
      cap_minutes: 780,
    }); // 103.8% > 100%, sobrecarga de 30 min
    const comfortableBand = makeWeeklyLoadBand({
      age_band: "10-12",
      planned_minutes: 240,
      cap_minutes: 600,
    });
    mockSummary([comfortableBand, overCapBand]);

    const { container } = renderComponent();

    expect(
      screen.getByText("30 min sobre el tope de 13-15 años. Revisa el plan de la semana."),
    ).toBeInTheDocument();

    // Copy asesor, nunca alarmista ("¡Exceso!" o similares están prohibidos).
    expect(screen.queryByText(/¡/)).not.toBeInTheDocument();
    expect(screen.queryByText(/[Ee]xceso/)).not.toBeInTheDocument();

    const fills = container.querySelectorAll<HTMLDivElement>(".rounded-full > .rounded-full");
    const overCapFill = fills[1];
    expect(overCapFill.style.backgroundColor).toBe("var(--color-danger)");
    // Nunca recortada/desbordada: el relleno SIEMPRE se capa a 100%, jamás
    // un valor > 100% (que desbordaría el track con `overflow-hidden`).
    expect(overCapFill.style.width).toBe("100%");
    const widthValue = Number.parseFloat(overCapFill.style.width);
    expect(widthValue).toBeLessThanOrEqual(100);
  });
});

describe("WeeklyLoadMeter — weekly_load ausente (null)", () => {
  it("omite la tile por completo, sin bloquear el resto de la página (FR-005 acceptance #3)", () => {
    mockSummary(null);

    const { container } = renderComponent();

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Carga semanal")).not.toBeInTheDocument();
    expect(screen.queryByText(/planificadas/)).not.toBeInTheDocument();
  });
});

describe("WeeklyLoadMeter — weekly_load vacío ([])", () => {
  it('renderiza la tile con la línea "Sin atletas en edad de seguimiento (10-15 años)" en vez de medidores', () => {
    mockSummary([]);

    renderComponent();

    expect(screen.getByText("Carga semanal")).toBeInTheDocument();
    expect(
      screen.getByText("Sin atletas en edad de seguimiento (10-15 años)"),
    ).toBeInTheDocument();

    // Sin medidores ni copy de estado.
    expect(screen.queryByText(/planificadas/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Cerca del tope/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sobre el tope/)).not.toBeInTheDocument();
  });
});

describe("WeeklyLoadMeter — esqueleto de carga", () => {
  it("muestra un esqueleto accesible mientras `isLoading` es true, sin renderizar datos", () => {
    mockUseCoachSummary.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useCoachSummary>);

    renderComponent();

    const status = screen.getByRole("status", { name: "Cargando carga semanal" });
    expect(status).toHaveAttribute("aria-busy", "true");

    expect(screen.queryByText(/planificadas/)).not.toBeInTheDocument();
    expect(screen.queryByText("Carga semanal")).not.toBeInTheDocument();
  });
});
