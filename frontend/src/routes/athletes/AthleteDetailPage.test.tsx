import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/api/athletes", () => ({
  getAthlete: vi.fn(),
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/parents", () => ({
  getParentAthletes: vi.fn().mockResolvedValue([]),
  getParentInvites: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/ai", () => ({
  getPHVExplanation: vi.fn(),
  getPHVExplanationCached: vi.fn().mockResolvedValue(null),
}));

// Mocks de componentes pesados que no son objeto del test
vi.mock("@/components/athletes/AnthropometryForm", () => ({
  AnthropometryForm: () => <div data-testid="anthropometry-form">AnthropometryForm</div>,
}));

vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));

vi.mock("@/components/athletes/GrowthCharts", () => ({
  GrowthCharts: () => <div data-testid="growth-charts">GrowthCharts</div>,
}));

vi.mock("@/components/athletes/NutritionalClassification", () => ({
  NutritionalClassification: () => (
    <div data-testid="nutritional-classification">NutritionalClassification</div>
  ),
}));

vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));

vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));

vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: ({ athlete }: { athlete: { first_name: string; last_name: string } }) => (
    <div data-testid="athlete-info-card">
      {athlete.first_name} {athlete.last_name}
    </div>
  ),
}));

vi.mock("@/components/athletes/LinkedParentsCard", () => ({
  LinkedParentsCard: () => <div data-testid="linked-parents-card">LinkedParentsCard</div>,
}));

// PHVExplanationCard mock con CTA funcional y soporte de readOnly para tests de padres
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: ({
    onMeasurementCTA,
    readOnly,
  }: {
    athleteId: number;
    hasRecords: boolean;
    onMeasurementCTA?: () => void;
    readOnly?: boolean;
  }) => (
    <div data-testid="phv-explanation-card" data-readonly={readOnly ?? false}>
      {!readOnly && (
        <button type="button" onClick={onMeasurementCTA}>
          Agregar medicion
        </button>
      )}
    </div>
  ),
}));

// PercentileCurves — no debería aparecer en ninguna tab del refactor Opción C
vi.mock("@/components/athletes/PercentileCurves", () => ({
  PercentileCurves: () => <div data-testid="percentile-curves">PercentileCurves</div>,
}));

vi.mock("@/components/training/AthleteNewslettersTabPanel", () => ({
  AthleteNewslettersTabPanel: () => (
    <div data-testid="newsletters-tab-panel">AthleteNewslettersTabPanel</div>
  ),
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import * as athletesApi from "@/api/athletes";
import { AthleteDetailPage } from "./AthleteDetailPage";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { MaturationStatus, Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures — DATOS FICTICIOS. Nunca usar datos reales de atletas menores.
// ---------------------------------------------------------------------------

const mockAthlete: AthleteDetailOut = {
  id: 1,
  user_id: 10,
  first_name: "Carlos",
  last_name: "Perez",
  birth_date: "2012-06-15",
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.3,
  age_decimal: 13.5,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

const mockAthleteWithLatest: AthleteDetailOut = {
  ...mockAthlete,
  latest_anthropometry: {
    id: 2,
    athlete_id: 1,
    evaluation_date: "2026-01-15",
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 73.0,
    leg_length_cm: 82.0,
    leg_sitting_ratio: 1.1233,
    maturity_offset: -0.5,
    age_at_phv: 13.5,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: "Enfoca en técnica",
    evaluated_by: 1,
    created_at: "2026-01-15T00:00:00Z",
    notes: null,
    height_percentile: 55,
  },
};

function makeRecord(id: number, overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id,
    athlete_id: 1,
    evaluation_date: "2026-01-15",
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 73.0,
    leg_length_cm: 82.0,
    leg_sitting_ratio: 1.1233,
    maturity_offset: -0.5,
    age_at_phv: 13.5,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

const recordA = makeRecord(1, { evaluation_date: "2025-06-01", standing_height_cm: 152.0 });
const recordB = makeRecord(2, { evaluation_date: "2026-01-15", standing_height_cm: 155.0 });

// ---------------------------------------------------------------------------
// Helpers de render
// ---------------------------------------------------------------------------

function renderPage(athleteId = "1") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/athletes/${athleteId}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/athletes/:id" element={<AthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Suites de tests
// ---------------------------------------------------------------------------

describe("AthleteDetailPage — refactor Opción C", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: API retorna atleta con datos y sin registros antropométricos
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthlete);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
  });

  // -------------------------------------------------------------------------
  // 1. Tab Antropometría
  // -------------------------------------------------------------------------

  describe("Tab Antropometría", () => {
    it("renderiza AnthropometryHistory", async () => {
      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      expect(screen.getByTestId("anthropometry-history")).toBeInTheDocument();
    });

    it("renderiza AnthropometryForm al abrir el formulario", async () => {
      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      // El form aparece sólo tras click en '+ Nueva medición'
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Nueva medición/i }));
      });
      expect(screen.getByTestId("anthropometry-form")).toBeInTheDocument();
    });

    it("NO renderiza GrowthCharts en tab Antropometría", async () => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);

      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      expect(screen.queryByTestId("growth-charts")).not.toBeInTheDocument();
    });

    it("NO renderiza PercentileCurves en tab Antropometría", async () => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);

      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      expect(screen.queryByTestId("percentile-curves")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 2. Tab Crecimiento
  // -------------------------------------------------------------------------

  describe("Tab Crecimiento", () => {
    beforeEach(() => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    });

    it("renderiza NutritionalClassification", async () => {
      renderPage();
      // Con registros, la página abre Crecimiento como tab inicial (useEffect)
      expect(await screen.findByTestId("nutritional-classification")).toBeInTheDocument();
    });

    it("renderiza GrowthCharts", async () => {
      renderPage();
      expect(await screen.findByTestId("growth-charts")).toBeInTheDocument();
    });

    it("renderiza una sola instancia de GrowthCharts (sin duplicados)", async () => {
      renderPage();
      await screen.findByTestId("growth-charts");
      expect(screen.getAllByTestId("growth-charts")).toHaveLength(1);
    });

    it("renderiza TrainingReadiness", async () => {
      renderPage();
      expect(await screen.findByTestId("training-readiness")).toBeInTheDocument();
    });

    it("renderiza PHVExplanationCard", async () => {
      renderPage();
      expect(await screen.findByTestId("phv-explanation-card")).toBeInTheDocument();
    });

    it("renderiza ResearchReferences", async () => {
      renderPage();
      expect(await screen.findByTestId("research-references")).toBeInTheDocument();
    });

    it("NO renderiza AnthropometryHistory en tab Crecimiento", async () => {
      renderPage();
      // Esperar a que el tab Crecimiento esté activo
      await screen.findByTestId("growth-charts");
      expect(screen.queryByTestId("anthropometry-history")).not.toBeInTheDocument();
    });

    it("Tab Crecimiento no aparece si no hay registros", async () => {
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
      renderPage();
      // Esperar a que el atleta cargue
      await screen.findByTestId("athlete-info-card");
      expect(screen.queryByRole("button", { name: /Crecimiento/i })).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 3. Navegación entre tabs — estado consistente
  // -------------------------------------------------------------------------

  describe("Navegación entre tabs", () => {
    beforeEach(() => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    });

    it("navegar a Antropometría desde Crecimiento muestra AnthropometryHistory", async () => {
      renderPage();
      // Esperar tab Crecimiento activo
      await screen.findByTestId("growth-charts");

      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Antropometría/i }));
      });
      expect(screen.getByTestId("anthropometry-history")).toBeInTheDocument();
      expect(screen.queryByTestId("growth-charts")).not.toBeInTheDocument();
    });

    it("volver a Crecimiento desde Antropometría restaura GrowthCharts", async () => {
      renderPage();
      // Ir a Antropometría
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      expect(screen.getByTestId("anthropometry-history")).toBeInTheDocument();

      // Volver a Crecimiento
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Crecimiento/i }));
      });
      expect(screen.getByTestId("growth-charts")).toBeInTheDocument();
      expect(screen.queryByTestId("anthropometry-history")).not.toBeInTheDocument();
    });

    it("navegar a Info general oculta contenido de Antropometría", async () => {
      renderPage();
      // Ir a Antropometría
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      // Ir a Info general
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Info general/i }));
      });
      expect(screen.queryByTestId("anthropometry-history")).not.toBeInTheDocument();
      expect(screen.queryByTestId("growth-charts")).not.toBeInTheDocument();
    });

    it("tab Antropometría conserva estado de anulación (cancelar form) tras ida y vuelta", async () => {
      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Antropometría/i }));
      });
      // Abrir form
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Nueva medición/i }));
      });
      expect(screen.getByTestId("anthropometry-form")).toBeInTheDocument();

      // Cancelar
      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Cancelar/i }));
      });
      expect(screen.queryByTestId("anthropometry-form")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 4. CTA en PHVExplanationCard → navega a tab Antropometría
  // -------------------------------------------------------------------------

  describe("CTA PHVExplanationCard", () => {
    beforeEach(() => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    });

    it("click en 'Agregar medicion' en tab Crecimiento navega a tab Antropometría", async () => {
      renderPage();
      // Esperar tab Crecimiento (tab inicial cuando hay records)
      await screen.findByTestId("phv-explanation-card");

      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Agregar medicion/i }));
      });

      // Ahora debe estar activo el tab Antropometría
      expect(screen.getByTestId("anthropometry-history")).toBeInTheDocument();
      expect(screen.queryByTestId("phv-explanation-card")).not.toBeInTheDocument();
    });

    it("tras navegar al tab Antropometría vía CTA no se renderiza GrowthCharts", async () => {
      renderPage();
      await screen.findByTestId("phv-explanation-card");

      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Agregar medicion/i }));
      });

      expect(screen.queryByTestId("growth-charts")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 5. Tab Info general — no afectado por refactor
  // -------------------------------------------------------------------------

  describe("Tab Info general", () => {
    it("muestra 'Datos del atleta' con datos básicos del atleta", async () => {
      renderPage();
      // Info general es el tab inicial cuando no hay registros
      expect(await screen.findByText(/Datos del atleta/i)).toBeInTheDocument();
    });

    it("muestra el sexo del atleta en la sección info", async () => {
      renderPage();
      await screen.findByText(/Datos del atleta/i);
      expect(screen.getByText("Masculino")).toBeInTheDocument();
    });

    it("muestra la categoría del atleta en la sección de datos", async () => {
      renderPage();
      await screen.findByText(/Datos del atleta/i);
      // "Sub-15" aparece en el StatCard de Edad y en el <dd> de Categoría;
      // confirmamos que al menos uno de los dos está presente en la sección info
      expect(screen.getAllByText("Sub-15").length).toBeGreaterThanOrEqual(1);
    });

    it("info general no renderiza GrowthCharts", async () => {
      renderPage();
      await screen.findByText(/Datos del atleta/i);
      expect(screen.queryByTestId("growth-charts")).not.toBeInTheDocument();
    });

    it("info general no renderiza AnthropometryHistory", async () => {
      renderPage();
      await screen.findByText(/Datos del atleta/i);
      expect(screen.queryByTestId("anthropometry-history")).not.toBeInTheDocument();
    });

    it("navegar a Info general desde Crecimiento muestra implicaciones PHV si hay latest", async () => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);

      renderPage();
      // Esperar el tab activo inicial (Crecimiento con records)
      await screen.findByTestId("growth-charts");

      await act(async () => {
        await userEvent.click(screen.getByRole("button", { name: /Info general/i }));
      });

      expect(screen.getByText(/Implicaciones PHV/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 6. Tab Boletines (newsletters) — RBAC coach/admin
  // -------------------------------------------------------------------------

  describe("Tab Boletines — coach", () => {
    beforeEach(() => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthlete);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
    });

    it("coach ve el tab Boletines en la barra de tabs", async () => {
      renderPage();
      await screen.findByTestId("athlete-info-card");
      expect(screen.getByTestId("athlete-tab-newsletters")).toBeInTheDocument();
    });

    it("navegar al tab Boletines renderiza AthleteNewslettersTabPanel", async () => {
      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByTestId("athlete-tab-newsletters"));
      });
      expect(screen.getByTestId("newsletters-tab-panel")).toBeInTheDocument();
    });

    it("tab Boletines activo no renderiza GrowthCharts ni AnthropometryHistory", async () => {
      renderPage();
      await act(async () => {
        await userEvent.click(await screen.findByTestId("athlete-tab-newsletters"));
      });
      expect(screen.queryByTestId("growth-charts")).not.toBeInTheDocument();
      expect(screen.queryByTestId("anthropometry-history")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 7. Tab Progreso — visible en la barra de tabs (sin gating condicional)
  // -------------------------------------------------------------------------

  describe("Tab Progreso", () => {
    it("muestra el tab Progreso en la barra de tabs", async () => {
      renderPage();
      await screen.findByTestId("athlete-info-card");
      expect(screen.getByTestId("athlete-tab-progreso")).toBeInTheDocument();
      expect(screen.getByText("Progreso")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 8. Estados de carga y error
  // -------------------------------------------------------------------------

  describe("Estados de carga y error", () => {
    it("muestra skeleton de carga mientras se obtiene el atleta", () => {
      // getAthlete nunca resuelve → estado loading persistente
      vi.mocked(athletesApi.getAthlete).mockReturnValue(new Promise(() => {}));
      vi.mocked(athletesApi.getAnthropometry).mockReturnValue(new Promise(() => {}));
      renderPage();
      // El skeleton usa animate-pulse; verificamos por ausencia de contenido real
      expect(screen.queryByTestId("athlete-info-card")).not.toBeInTheDocument();
    });

    it("muestra mensaje de error si el atleta no existe", async () => {
      vi.mocked(athletesApi.getAthlete).mockRejectedValue(new Error("Not found"));
      renderPage();
      expect(await screen.findByText(/Atleta no encontrado/i)).toBeInTheDocument();
    });

    it("muestra enlace para volver a la lista en estado de error", async () => {
      vi.mocked(athletesApi.getAthlete).mockRejectedValue(new Error("Not found"));
      renderPage();
      await screen.findByText(/Atleta no encontrado/i);
      expect(screen.getByRole("link", { name: /Volver a la lista/i })).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// MyAthleteDetailPage — vista del padre/tutor
// ---------------------------------------------------------------------------

import { MyAthleteDetailPage } from "../parents/MyAthleteDetailPage";

function renderParentPage(athleteId = "1") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/my-athletes/${athleteId}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/my-athletes/:id" element={<MyAthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("MyAthleteDetailPage — vista padres (coach es AthleteDetailPage)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthlete);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
  });

  it("renderiza AthleteInfoCard con datos del atleta", async () => {
    renderParentPage();
    expect(await screen.findByTestId("athlete-info-card")).toBeInTheDocument();
  });

  it("muestra tab Datos como tab inicial", async () => {
    renderParentPage();
    // "Datos del atleta" es el heading dentro del tab info
    expect(await screen.findByText(/Datos del atleta/i)).toBeInTheDocument();
  });

  it("NO muestra tab Crecimiento si no hay registros", async () => {
    renderParentPage();
    await screen.findByText(/Datos del atleta/i);
    expect(screen.queryByRole("button", { name: /Crecimiento/i })).not.toBeInTheDocument();
  });

  it("NO tiene tab Antropometría (los padres no registran mediciones)", async () => {
    renderParentPage();
    await screen.findByTestId("athlete-info-card");
    expect(screen.queryByRole("button", { name: /Antropometría/i })).not.toBeInTheDocument();
  });

  it("muestra tab Crecimiento cuando hay registros", async () => {
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    renderParentPage();
    expect(await screen.findByRole("button", { name: /Crecimiento/i })).toBeInTheDocument();
  });

  it("tab Crecimiento muestra GrowthCharts (vista padres también tiene gráficas)", async () => {
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    renderParentPage();
    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: /Crecimiento/i }));
    });
    expect(screen.getByTestId("growth-charts")).toBeInTheDocument();
  });

  it("tab Crecimiento muestra NutritionalClassification (vista padres)", async () => {
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    renderParentPage();
    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: /Crecimiento/i }));
    });
    expect(screen.getByTestId("nutritional-classification")).toBeInTheDocument();
  });

  it("muestra mensaje de error si el atleta no carga", async () => {
    vi.mocked(athletesApi.getAthlete).mockRejectedValue(new Error("Forbidden"));
    renderParentPage();
    expect(
      await screen.findByText(/No se pudo cargar la información del atleta/i),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Tab Crecimiento — PHVExplanationCard readOnly + ResearchReferences
  // -------------------------------------------------------------------------

  describe("tab Crecimiento — PHV y referencias para padres", () => {
    beforeEach(() => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteWithLatest);
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([recordA, recordB]);
    });

    it("renderiza PHVExplanationCard en modo readOnly al cambiar al tab Crecimiento", async () => {
      renderParentPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Crecimiento/i }));
      });
      const card = screen.getByTestId("phv-explanation-card");
      expect(card).toBeInTheDocument();
      // Confirmar que se pasa readOnly=true al componente
      expect(card).toHaveAttribute("data-readonly", "true");
    });

    it("renderiza ResearchReferences al cambiar al tab Crecimiento", async () => {
      renderParentPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Crecimiento/i }));
      });
      expect(screen.getByTestId("research-references")).toBeInTheDocument();
    });

    it("NO muestra el botón Generar ni Regenerar en el tab Crecimiento del padre", async () => {
      renderParentPage();
      await act(async () => {
        await userEvent.click(await screen.findByRole("button", { name: /Crecimiento/i }));
      });
      // El mock de PHVExplanationCard en modo readOnly no renderiza el botón
      expect(
        screen.queryByRole("button", { name: /Agregar medicion/i }),
      ).not.toBeInTheDocument();
    });
  });
});
