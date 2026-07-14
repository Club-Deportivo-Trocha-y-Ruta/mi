/**
 * Tests vitest — AnalyzeAthleteButton (botón compartido "Analizar con IA").
 *
 * Cubre:
 *  - Render básico: botón visible con testid y label (default y custom).
 *  - aria-label descriptivo con el nombre del deportista.
 *  - Touch target: min-h-[48px] y min-w-[48px] (constitución III — regresión).
 *  - jest-axe: 0 violaciones de accesibilidad en el estado por defecto.
 *  - Rename table (feature 033 / T054, T047): ícono Sparkles (no
 *    BrainCircuit), label exacto "Analizar con IA", título del modal de
 *    confirmación "Re-ejecutar análisis con IA".
 *  - Pista pre-lanzamiento de presupuesto/concurrencia (feature 033 / T055,
 *    T051): las tres presentaciones de `budget_status`, la pista de espera
 *    por concurrencia y la degradación con gracia cuando falla el fetch de
 *    `GET /api/ai/status`.
 *  - jest-axe adicional (feature 033 / T056) sobre el estado con hint de
 *    presupuesto agotado (botón deshabilitado + `role="alert"`).
 *
 * Los flujos completos de launch / confirmación / éxito / error ya están
 * cubiertos indirectamente vía InsightsTabAnalyze.test.tsx (InsightsTab) y
 * ResultsTable.test.tsx — este suite ejercita el componente en aislamiento.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

import type { AIStatusResponse } from "@/types/ai.types";

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

// useAIStatus (T051) — sin datos por defecto: degradación reactiva-only,
// ningún hint visible, comportamiento idéntico al pre-existente.
let mockAIStatusData: AIStatusResponse | undefined = undefined;
let mockAIStatusIsError = false;
vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: mockAIStatusData, isError: mockAIStatusIsError }),
}));

// useAthleteRunOutcome (FR-013) — sin desenlace de fallo por defecto; el
// seguimiento del run tiene su propio suite (useAthleteRunOutcome.test.ts).
let mockRunFailureMessage: string | null = null;
vi.mock("@/hooks/ai/useAthleteRunOutcome", () => ({
  useAthleteRunOutcome: () => ({ failureMessage: mockRunFailureMessage }),
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
  mockAIStatusData = undefined;
  mockAIStatusIsError = false;
  mockRunFailureMessage = null;
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
// Desenlace del run (FR-013) — el fallo terminal reemplaza el estado optimista
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — desenlace del run (FR-013)", () => {
  it("cuando useAthleteRunOutcome reporta failureMessage, muestra el error (no el botón)", () => {
    mockRunFailureMessage = "El análisis de Corredor A falló. Intenta de nuevo.";
    renderButton();

    const error = screen.getByTestId("ai-launch-error-55");
    expect(error).toHaveAttribute("role", "alert");
    expect(error).toHaveTextContent(
      "El análisis de Corredor A falló. Intenta de nuevo.",
    );
    // El botón de lanzamiento ya no está en pantalla.
    expect(screen.queryByTestId("ai-launch-btn-55")).not.toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// Rename table (feature 033 / T054, regresión T047)
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — rename table (T054, regresión T047)", () => {
  it('el label por defecto es exactamente "Analizar con IA" (no solo "Analizar")', () => {
    renderButton();
    expect(screen.getByTestId("ai-launch-btn-55")).toHaveTextContent(
      "Analizar con IA",
    );
  });

  it("usa el ícono Sparkles, no BrainCircuit", () => {
    renderButton();
    const btn = screen.getByTestId("ai-launch-btn-55");
    expect(btn.querySelector("svg.lucide-sparkles")).toBeInTheDocument();
    expect(btn.querySelector("svg.lucide-brain-circuit")).not.toBeInTheDocument();
  });

  it('el modal de confirmación de re-run se titula "Re-ejecutar análisis con IA"', async () => {
    const user = userEvent.setup();
    // insightFreshness=null → insight fresco existente → confirmar antes de re-correr.
    renderButton({ insightFreshness: null });
    await user.click(screen.getByTestId("ai-launch-btn-55"));
    expect(
      await screen.findByRole("alertdialog", { name: "Re-ejecutar análisis con IA" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("alertdialog", { name: "Re-ejecutar análisis" }),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Pista pre-lanzamiento de presupuesto/concurrencia (feature 033 / T055, T051)
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — pista pre-lanzamiento de IA (T055)", () => {
  it("budget_status='ok' + concurrencia disponible + sin ETA: no muestra ningún hint más allá del botón", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 80,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    renderButton();
    expect(screen.queryByTestId("ai-budget-hint-warning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-exhausted")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-concurrency")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-duration")).not.toBeInTheDocument();
    // El botón sigue habilitado.
    expect(screen.getByTestId("ai-launch-btn-55")).not.toBeDisabled();
  });

  it("budget_status='ok' con ETA>0 muestra el hint neutro '≈Ns', launch sigue habilitado", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 80,
      concurrency_available: true,
      est_wait_seconds: 18,
    };
    renderButton();
    expect(screen.getByTestId("ai-budget-hint-duration")).toHaveTextContent("≈18s");
    expect(screen.getByTestId("ai-launch-btn-55")).not.toBeDisabled();
  });

  it("budget_status='warning' muestra el hint ámbar con % restante, launch sigue habilitado", () => {
    mockAIStatusData = {
      budget_status: "warning",
      budget_remaining_pct: 12,
      concurrency_available: true,
      est_wait_seconds: 20,
    };
    renderButton();
    expect(screen.getByTestId("ai-budget-hint-warning")).toHaveTextContent(
      "Presupuesto de IA: 12% restante",
    );
    expect(screen.getByTestId("ai-launch-btn-55")).not.toBeDisabled();
  });

  it("budget_status='exhausted' deshabilita el botón y muestra la explicación ANTES de cualquier click", () => {
    mockAIStatusData = {
      budget_status: "exhausted",
      budget_remaining_pct: 0,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    renderButton();
    const btn = screen.getByTestId("ai-launch-btn-55");
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("ai-budget-hint-exhausted")).toHaveTextContent(
      "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo.",
    );
    // El aria-label también refleja el estado agotado.
    expect(btn).toHaveAttribute(
      "aria-label",
      "Presupuesto de IA agotado — no se puede analizar a Corredor A",
    );
  });

  it("un click no dispara mutate() cuando budget_status='exhausted'", async () => {
    const user = userEvent.setup();
    mockAIStatusData = {
      budget_status: "exhausted",
      budget_remaining_pct: 0,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    renderButton();
    await user.click(screen.getByTestId("ai-launch-btn-55"));
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("concurrency_available=false muestra 'Alta demanda — espera ≈Ns', launch sigue habilitado", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 90,
      concurrency_available: false,
      est_wait_seconds: 45,
    };
    renderButton();
    expect(screen.getByTestId("ai-budget-hint-concurrency")).toHaveTextContent(
      "Alta demanda — espera ≈45s",
    );
    expect(screen.getByTestId("ai-launch-btn-55")).not.toBeDisabled();
  });

  it("degrada con gracia cuando GET /api/ai/status falla — sin hint, botón sigue funcional", async () => {
    const user = userEvent.setup();
    mockAIStatusData = undefined;
    mockAIStatusIsError = true;
    renderButton();

    // Ningún hint de presupuesto/concurrencia se renderiza.
    expect(screen.queryByTestId("ai-budget-hint-warning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-exhausted")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-concurrency")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-duration")).not.toBeInTheDocument();

    // El botón nunca queda bloqueado por el fallo de useAIStatus() — sigue
    // funcionando de forma reactiva (comportamiento pre-existente).
    const btn = screen.getByTestId("ai-launch-btn-55");
    expect(btn).not.toBeDisabled();
    await user.click(btn);
    expect(mockMutate).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// jest-axe adicional sobre estados con hint (feature 033 / T056)
// ---------------------------------------------------------------------------

describe("AnalyzeAthleteButton — accesibilidad de estados con hint (T056)", () => {
  it("jest-axe: 0 violaciones con budget_status='exhausted' (botón deshabilitado + alert)", async () => {
    mockAIStatusData = {
      budget_status: "exhausted",
      budget_remaining_pct: 0,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    const { container } = renderButton();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("jest-axe: 0 violaciones con budget_status='warning'", async () => {
    mockAIStatusData = {
      budget_status: "warning",
      budget_remaining_pct: 15,
      concurrency_available: true,
      est_wait_seconds: 10,
    };
    const { container } = renderButton();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
