import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { DashboardPage } from "@/routes/dashboard/DashboardPage";
import type { AlertsSummary } from "@/types/alerts.types";

// ---------------------------------------------------------------------------
// Mock de la capa API: simula que el backend ya filtró las alertas al club
// del entrenador autenticado (club X). Ningún atleta de otro club (club Y)
// ni el atleta semilla de pruebas de consentimiento debe llegar aquí.
// ---------------------------------------------------------------------------

const CLUB_X_ALERTS: AlertsSummary = {
  overdue: 1,
  due_soon: 0,
  ok: 1,
  never_measured: 0,
  rapid_growth_count: 0,
  athletes: [
    {
      athlete_id: 101,
      athlete_name: "Mateo Restrepo Ficticio",
      sex: "M",
      age_decimal: 12.4,
      category: "Pre-juvenil A",
      measurement_status: "overdue",
      last_measurement_date: "2026-01-15",
      next_due_date: "2026-04-15",
      days_overdue: 30,
      current_phv_status: "Pre-PHV",
      measurement_interval_days: 90,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
    {
      athlete_id: 102,
      athlete_name: "Sofía Muñoz Ficticia",
      sex: "F",
      age_decimal: 13.1,
      category: "Juvenil",
      measurement_status: "ok",
      last_measurement_date: "2026-06-01",
      next_due_date: "2026-09-01",
      days_overdue: null,
      current_phv_status: "Circa-PHV",
      measurement_interval_days: 90,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
  ],
};

// Nombres que NUNCA deben aparecer: atletas de otro club (club Y) ni el
// atleta semilla usado en pruebas de consentimiento (incluye payload XSS
// de prueba, que tampoco debe reflejarse literalmente en el DOM).
const FORBIDDEN_NAMES = ["Club Y Atleta Ficticio", "ConsentTest", "<script>alert(1)</script> Test"];

vi.mock("@/api/alerts", () => ({
  getAlerts: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (state: { accessToken: string }) => unknown) =>
    selector({ accessToken: "fake-token" }),
}));

import { getAlerts } from "@/api/alerts";

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardPage — aislamiento de club (cross-club isolation)", () => {
  it("solo renderiza atletas del club del entrenador autenticado, nunca datos de otro club o de fixtures de otras pruebas", async () => {
    vi.mocked(getAlerts).mockResolvedValue(CLUB_X_ALERTS);

    renderDashboard();

    // Datos legítimos del club X deben aparecer
    expect(await screen.findByText("Mateo Restrepo Ficticio")).toBeInTheDocument();

    // Ningún nombre prohibido (otro club / fixtures de otras pruebas) debe
    // aparecer en ningún bloque del dashboard: tarjetas resumen, chips de
    // MeasurementAlerts, bloque de crecimiento acelerado o lista de acción.
    for (const forbiddenName of FORBIDDEN_NAMES) {
      expect(screen.queryByText(forbiddenName, { exact: false })).not.toBeInTheDocument();
    }

    // El DOM completo tampoco debe contener el marcador crudo, ni siquiera
    // fuera de un nodo de texto (defensa en profundidad contra fugas via
    // atributos/innerHTML).
    expect(document.body.innerHTML).not.toContain("ConsentTest");
    expect(document.body.innerHTML).not.toContain("Club Y Atleta Ficticio");
  });

  it("useAlerts no envía club_id — la delimitación por club depende exclusivamente del backend vía JWT", async () => {
    vi.mocked(getAlerts).mockResolvedValue(CLUB_X_ALERTS);

    renderDashboard();

    await screen.findByText("Mateo Restrepo Ficticio");

    // Documenta y protege contra una futura regresión donde alguien intente
    // enviar club_id explícito en el frontend en vez de confiar en el
    // scope del token del entrenador autenticado.
    expect(getAlerts).toHaveBeenCalledWith(undefined);
  });
});
