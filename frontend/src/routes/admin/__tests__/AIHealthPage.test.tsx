/**
 * Tests de AIHealthPage (feature 041 — gobernanza multi-coach, US6, T079).
 * Contrato: specs/041-multi-coach-governance/contracts/scope-ai-imports.md
 * §7.3, §11.3 #20.
 *
 * Cubre la sección de gasto de IA por entrenador: carga (skeleton), vacío,
 * error con "Reintentar" funcional, cold start, y que la fila "Total del
 * club" sea la suma de las filas — todo independiente de `useAIHealth`
 * (una consulta puede fallar sin ocultar el resultado de la otra). Cero
 * violaciones de jest-axe en cargado y vacío.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";

expect.extend(toHaveNoViolations);

import { AIHealthPage } from "@/routes/admin/AIHealthPage";

const HEALTH_URL = "*/api/ai/health";
const USAGE_URL = "*/api/race-analysis/admin/ai-usage";

function healthHandler() {
  return http.get(HEALTH_URL, () =>
    HttpResponse.json({ enabled: true, provider: "google", model: "gemini-3.8-flash" }),
  );
}

function usageHandler(byCoach: unknown[]) {
  return http.get(USAGE_URL, () =>
    HttpResponse.json({
      window_days: 30,
      run_count: 12,
      cost_usd_total: 3.4712,
      latency_ms_p50: 42000,
      latency_ms_p95: 91000,
      fail_rate: 0.0833,
      by_prompt_version: [],
      by_coach: byCoach,
    }),
  );
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <AIHealthPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mswServer.use(healthHandler());
});

describe("AIHealthPage — gasto de IA por entrenador", () => {
  it("muestra skeleton de carga con anuncio accesible", async () => {
    mswServer.use(
      http.get(USAGE_URL, async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json({
          window_days: 30,
          run_count: 0,
          cost_usd_total: 0,
          latency_ms_p50: 0,
          latency_ms_p95: 0,
          fail_rate: 0,
          by_prompt_version: [],
          by_coach: [],
        });
      }),
    );
    renderPage();

    const loading = await screen.findByTestId("ai-spend-by-coach-loading");
    expect(loading).toHaveAttribute("role", "status");
    expect(loading).toHaveAttribute("aria-live", "polite");

    await waitFor(() =>
      expect(screen.queryByTestId("ai-spend-by-coach-loading")).not.toBeInTheDocument(),
    );
  });

  it("renderiza la tabla por entrenador y una fila total que suma las filas", async () => {
    mswServer.use(
      usageHandler([
        { user_id: 3, display_name: "Ana Coach", run_count: 8, cost_usd_total: 2.4012 },
        { user_id: 7, display_name: "Beto Coach", run_count: 3, cost_usd_total: 1.07 },
        { user_id: null, display_name: "Sin atribuir", run_count: 1, cost_usd_total: 0 },
      ]),
    );
    renderPage();

    const table = await screen.findByTestId("ai-spend-by-coach-table");
    expect(within(table).getByText("Ana Coach")).toBeInTheDocument();
    expect(within(table).getByText("Beto Coach")).toBeInTheDocument();
    expect(within(table).getByText("Sin atribuir")).toBeInTheDocument();

    const totalRow = screen.getByTestId("ai-spend-row-total");
    expect(within(totalRow).getByText("Total del club")).toBeInTheDocument();
    // 8 + 3 + 1 = 12 análisis; 2.4012 + 1.07 + 0 = 3.4712 USD.
    expect(within(totalRow).getByText("12")).toBeInTheDocument();
    expect(within(totalRow).getByText("$3.4712")).toBeInTheDocument();
  });

  it("estado vacío: sin CTA, nunca una tabla con cuerpo vacío", async () => {
    mswServer.use(usageHandler([]));
    renderPage();

    expect(
      await screen.findByText("Aún no hay gasto registrado en esta ventana."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("ai-spend-by-coach-table")).not.toBeInTheDocument();
  });

  it("estado de error: copy de reintento y refetch funcional", async () => {
    let calls = 0;
    mswServer.use(
      http.get(USAGE_URL, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return HttpResponse.json({
          window_days: 30,
          run_count: 1,
          cost_usd_total: 0.5,
          latency_ms_p50: 0,
          latency_ms_p95: 0,
          fail_rate: 0,
          by_prompt_version: [],
          by_coach: [{ user_id: 3, display_name: "Ana Coach", run_count: 1, cost_usd_total: 0.5 }],
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByText("No se pudo cargar el gasto de IA. Intenta de nuevo."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /reintentar/i }));

    await screen.findByTestId("ai-spend-by-coach-table");
    expect(calls).toBe(2);
  });

  it("estado cold start: variante calmada, nunca un spinner sin contexto", async () => {
    mswServer.use(
      http.get(USAGE_URL, () => HttpResponse.error()),
    );
    renderPage();

    expect(
      await screen.findByText(
        "La aplicación está iniciando, puede tardar unos segundos. Intenta de nuevo en un momento.",
      ),
    ).toBeInTheDocument();
  });

  it("un fallo en el gasto de IA no oculta la tarjeta de proveedor/modelo", async () => {
    mswServer.use(http.get(USAGE_URL, () => HttpResponse.error()));
    renderPage();

    expect(await screen.findByText("google")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "La aplicación está iniciando, puede tardar unos segundos. Intenta de nuevo en un momento.",
      ),
    ).toBeInTheDocument();
  });
});

describe("AIHealthPage — accesibilidad (jest-axe)", () => {
  it("sin violaciones: cargado con filas", async () => {
    mswServer.use(
      usageHandler([
        { user_id: 3, display_name: "Ana Coach", run_count: 8, cost_usd_total: 2.4012 },
      ]),
    );
    const { container } = renderPage();
    await screen.findByTestId("ai-spend-by-coach-table");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones: vacío", async () => {
    mswServer.use(usageHandler([]));
    const { container } = renderPage();
    await screen.findByText("Aún no hay gasto registrado en esta ventana.");
    expect(await axe(container)).toHaveNoViolations();
  });
});
