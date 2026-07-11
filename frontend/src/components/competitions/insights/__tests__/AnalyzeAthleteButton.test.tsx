/**
 * Tests vitest — AnalyzeAthleteButton (botón compartido "Analizar con IA").
 *
 * Cubre:
 *  - Render básico: botón visible con testid y label (default y custom).
 *  - aria-label descriptivo con el nombre del deportista.
 *  - Touch target: min-h-[48px] y min-w-[48px] (constitución III — regresión).
 *  - jest-axe: 0 violaciones de accesibilidad en el estado por defecto.
 *
 * Los flujos completos de launch / confirmación / éxito / error ya están
 * cubiertos indirectamente vía InsightsTabAnalyze.test.tsx (InsightsTab) y
 * ResultsTable.test.tsx — este suite ejercita el componente en aislamiento.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockMutate = vi.fn();
let mockIsPending = false;
vi.mock("@/hooks/athletes/useLaunchAthleteAnalysis", () => ({
  useLaunchAthleteAnalysis: (_athleteId: number) => ({
    mutate: mockMutate,
    isPending: mockIsPending,
  }),
}));

import { AnalyzeAthleteButton } from "@/components/competitions/insights/AnalyzeAthleteButton";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderButton(
  overrides: Partial<React.ComponentProps<typeof AnalyzeAthleteButton>> = {},
) {
  return render(
    <MemoryRouter>
      <AnalyzeAthleteButton
        athleteId={55}
        season={2026}
        validaNum={4}
        insightFreshness={undefined}
        displayName="Corredor A"
        {...overrides}
      />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
});

// ---------------------------------------------------------------------------
// Render básico
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — render básico", () => {
  it("renderiza el botón con el testid y label por defecto", () => {
    renderButton();
    const btn = screen.getByTestId("ai-launch-btn-55");
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveTextContent("Analizar");
  });

  it("usa el label custom cuando se pasa la prop `label`", () => {
    renderButton({ label: "Re-analizar" });
    expect(screen.getByTestId("ai-launch-btn-55")).toHaveTextContent(
      "Re-analizar",
    );
  });

  it("expone un aria-label descriptivo con el nombre del deportista", () => {
    renderButton();
    expect(screen.getByTestId("ai-launch-btn-55")).toHaveAttribute(
      "aria-label",
      "Analizar con IA a Corredor A",
    );
  });
});

// ---------------------------------------------------------------------------
// Touch target — regresión tamaño mínimo 48x48px
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — touch target (min 48x48px)", () => {
  it("el botón tiene min-h-[48px] y min-w-[48px]", () => {
    renderButton();
    const btn = screen.getByTestId("ai-launch-btn-55");
    expect(btn).toHaveClass("min-h-[48px]");
    expect(btn).toHaveClass("min-w-[48px]");
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad (axe)
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — accesibilidad", () => {
  it("jest-axe: 0 violaciones en el estado por defecto", async () => {
    const { container } = renderButton();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
