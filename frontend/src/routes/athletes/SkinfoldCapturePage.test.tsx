/**
 * Tests — SkinfoldCapturePage (feature 046, US1, T019/T029).
 *
 * Escrito antes de T029 (TDD, tasks.md): falla hasta que
 * `SkinfoldCapturePage.tsx` exista con esta forma. Contrato asumido: la
 * página lee `:id`/`:recordId` de la ruta, carga la evaluación con
 * `getAnthropometry` (`@/api/athletes`), calcula la edad del deportista en
 * la fecha de la evaluación (`age_decimal` del atleta si ≥ 9 no aplica
 * directo — se asume que la página usa `record.evaluation_date` contra la
 * fecha de nacimiento del atleta) y redirige con un toast si es menor de 9;
 * si no, renderiza `SkinfoldWizard`.
 *
 * Datos: sintéticos, sin nombre de ningún deportista real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/api/athletes", () => ({
  getAthlete: vi.fn(),
  getAnthropometry: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import * as athletesApi from "@/api/athletes";
import { toast } from "sonner";
import { SkinfoldCapturePage } from "@/routes/athletes/SkinfoldCapturePage";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { MaturationStatus } from "@/types/enums";

const ATHLETE_ID = 17;
const RECORD_ID = 812;

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: RECORD_ID,
    athlete_id: ATHLETE_ID,
    evaluation_date: "2026-09-20",
    weight_kg: 42.0,
    standing_height_cm: 150.0,
    arm_span_cm: 151.0,
    sitting_height_cm: 75.0,
    leg_length_cm: 75.0,
    leg_sitting_ratio: 1.0,
    maturity_offset: -1.0,
    age_at_phv: 12.5,
    maturation_status: MaturationStatus.PrePHV,
    ...overrides,
  } as AnthropometricRecord;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter
        initialEntries={[`/athletes/${ATHLETE_ID}/anthropometry/${RECORD_ID}/skinfolds`]}
      >
        <Routes>
          <Route
            path="/athletes/:id/anthropometry/:recordId/skinfolds"
            element={<SkinfoldCapturePage />}
          />
          <Route path="/athletes/:id" element={<div>Perfil del atleta</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(athletesApi.getAnthropometry).mockReset();
  vi.mocked(toast.error).mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("SkinfoldCapturePage", () => {
  it("renderiza el asistente de pliegues cuando el atleta tiene 9 años o más en la fecha de evaluación", async () => {
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([
      makeRecord({ evaluation_date: "2026-09-20" }),
    ]);
    renderPage();

    expect(await screen.findByText("Antes de empezar")).toBeInTheDocument();
  });

  it("redirige a /athletes/:id?tab=growth con un toast cuando el atleta es menor de 9 años", async () => {
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([
      makeRecord({ evaluation_date: "2026-09-20", age_at_phv: 6.0 }),
    ]);
    renderPage();

    expect(await screen.findByText("Perfil del atleta")).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalled();
  });

  it("sin violaciones de accesibilidad (axe) en el estado cargado", async () => {
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([
      makeRecord({ evaluation_date: "2026-09-20" }),
    ]);
    const { container } = renderPage();
    await screen.findByText("Antes de empezar");
    expect(await axe(container)).toHaveNoViolations();
  });
});
