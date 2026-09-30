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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/api/athletes", () => ({
  getAthlete: vi.fn(),
  getAnthropometry: vi.fn(),
}));

// Mock parcial (feature 048, T046): `saveSkinfolds` para terminar el
// asistente por el camino «Hoy prefiere no medirse».
vi.mock("@/api/bodyComposition", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/bodyComposition")>()),
  saveSkinfolds: vi.fn(),
  downloadFieldGuide: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import * as athletesApi from "@/api/athletes";
import { saveSkinfolds } from "@/api/bodyComposition";
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

function renderPage(search = "") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter
        initialEntries={[`/athletes/${ATHLETE_ID}/anthropometry/${RECORD_ID}/skinfolds${search}`]}
      >
        <Routes>
          <Route
            path="/athletes/:id/anthropometry/:recordId/skinfolds"
            element={<SkinfoldCapturePage />}
          />
          <Route path="/athletes/:id" element={<div>Perfil del atleta</div>} />
          <Route path="/anthropometry/session" element={<div>Cola de la jornada</div>} />
          <Route path="*" element={<div>Otra ruta</div>} />
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

  describe("returnTo (feature 048, T046)", () => {
    const loaded = () =>
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([
        makeRecord({ evaluation_date: "2026-09-20" }),
      ]);

    it("con returnTo=/anthropometry/session, «Volver a la jornada» apunta a la cola (cancelar)", async () => {
      loaded();
      renderPage("?returnTo=/anthropometry/session");
      await screen.findByText("Antes de empezar");
      expect(screen.getByRole("link", { name: /Volver a la jornada/ })).toHaveAttribute(
        "href",
        "/anthropometry/session",
      );
    });

    it("al terminar vuelve a la cola de la jornada", async () => {
      const user = userEvent.setup();
      loaded();
      vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
      renderPage("?returnTo=/anthropometry/session");
      await screen.findByText("Antes de empezar");
      await user.click(screen.getByRole("button", { name: "Hoy prefiere no medirse" }));
      expect(await screen.findByText("Cola de la jornada")).toBeInTheDocument();
    });

    it("sin returnTo, al terminar vuelve al perfil", async () => {
      const user = userEvent.setup();
      loaded();
      vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
      renderPage();
      await screen.findByText("Antes de empezar");
      await user.click(screen.getByRole("button", { name: "Hoy prefiere no medirse" }));
      expect(await screen.findByText("Perfil del atleta")).toBeInTheDocument();
    });

    it.each([
      "https://evil.example.com",
      "//evil.example.com",
      "/anthropometry/session/../../admin",
      "/anthropometry/session?x=1",
      "/athletes",
    ])("rechaza returnTo=%s y usa el perfil", async (target) => {
      const user = userEvent.setup();
      loaded();
      vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
      renderPage(`?returnTo=${encodeURIComponent(target)}`);
      await screen.findByText("Antes de empezar");
      expect(screen.getByRole("link", { name: /Volver al perfil/ })).toHaveAttribute(
        "href",
        `/athletes/${ATHLETE_ID}?tab=growth`,
      );
      await user.click(screen.getByRole("button", { name: "Hoy prefiere no medirse" }));
      expect(await screen.findByText("Perfil del atleta")).toBeInTheDocument();
    });

    it("menor de 9 con returnTo redirige a la cola", async () => {
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([
        makeRecord({ evaluation_date: "2026-09-20", age_at_phv: 6.0 }),
      ]);
      renderPage("?returnTo=/anthropometry/session");
      await waitFor(() => expect(screen.getByText("Cola de la jornada")).toBeInTheDocument());
    });
  });
});
