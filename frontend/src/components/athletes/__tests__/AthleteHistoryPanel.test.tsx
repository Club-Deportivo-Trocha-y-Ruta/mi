/**
 * Tests de AthleteHistoryPanel (feature 041 — gobernanza multi-coach, T038).
 * Contrato: specs/041-multi-coach-governance/contracts/coach-activity-report.md §8.1.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  athleteAuditLogHandler,
  makeAuditEntry,
  makeAuditListOut,
} from "@/test/msw/auditHandlers";

import { AthleteHistoryPanel } from "../AthleteHistoryPanel";

function renderPanel(role: "coach" | "admin" | "parent" | "athlete" = "coach") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AthleteHistoryPanel athleteId={42} role={role} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mswServer.use(athleteAuditLogHandler);
});

describe("AthleteHistoryPanel", () => {
  it("no renderiza nada para el rol parent (defensa en profundidad)", () => {
    const { container } = renderPanel("parent");
    expect(container).toBeEmptyDOMElement();
  });

  it("renderiza las filas de historial para coach", async () => {
    renderPanel("coach");

    expect(
      await screen.findByText("Ana Coach actualizó la sesión de entrenamiento."),
    ).toBeInTheDocument();
  });

  it("muestra el vacío cuando no hay cambios registrados", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/audit-log", () =>
        HttpResponse.json(makeAuditListOut({ items: [], total: 0 })),
      ),
    );

    renderPanel("coach");

    expect(
      await screen.findByText(
        "Todavía no hay cambios registrados para este deportista.",
      ),
    ).toBeInTheDocument();
  });

  it("muestra 'Ver más' cuando hay más de 15 registros y aumenta el límite al hacer clic", async () => {
    const observedLimits: string[] = [];
    mswServer.use(
      http.get("*/api/athletes/:athleteId/audit-log", ({ request }) => {
        const limit = new URL(request.url).searchParams.get("limit") ?? "15";
        observedLimits.push(limit);
        return HttpResponse.json(
          makeAuditListOut({
            items: [makeAuditEntry()],
            total: 20,
            limit: Number(limit),
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderPanel("coach");

    const verMasButton = await screen.findByRole("button", { name: "Ver más" });
    await user.click(verMasButton);

    await waitFor(() => expect(observedLimits).toContain("30"));
  });

  it("no muestra 'Ver más' cuando todos los registros ya están cargados", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/audit-log", () =>
        HttpResponse.json(makeAuditListOut({ items: [makeAuditEntry()], total: 1 })),
      ),
    );

    renderPanel("coach");

    await screen.findByText("Ana Coach actualizó la sesión de entrenamiento.");
    expect(screen.queryByRole("button", { name: "Ver más" })).not.toBeInTheDocument();
  });
});
