/**
 * Tests de IdentityReviewPage — revisión de identidad del histórico
 * (feature 044, US4, T053).
 *
 * Cubre: pendientes, vacío, error, resume (progreso refleja lo ya decidido),
 * deshacer, 409 al decidir, atajo de teclado; cero violaciones axe en la
 * página y en el diálogo de confirmación.
 *
 * Nombres siempre sintéticos ("Ana Prueba Uno") — nunca datos reales de un
 * menor, ni en fixtures de test.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// jsdom no implementa estos métodos de Pointer Events — Radix Select
// (usado para el filtro de estado) los invoca al abrir/cerrar el listbox.
// Mismo workaround que el resto de la suite usa para Radix en jsdom.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

import { toast } from "sonner";
import { mswServer } from "@/test/setup";
import {
  makeCandidatesResponse,
  makeIdentityCandidate,
  makeSummaryResponse,
  raceIdentityDecideConflictHandler,
  raceIdentityEmptyHandler,
  raceIdentityDecideLinkedAmbiguousHandler,
  raceIdentityEmptySummaryHandler,
  raceIdentityErrorHandler,
  raceIdentityHandlers,
} from "@/test/msw/raceIdentityHandlers";
import { IdentityReviewPage } from "@/routes/competitions/history/IdentityReviewPage";
import { delay, http, HttpResponse } from "msw";

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/identity-review"]}>
        <Routes>
          <Route
            path="/competitions/identity-review"
            element={<IdentityReviewPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IdentityReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...raceIdentityHandlers);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("modo pendientes: muestra el primer candidato con dos tarjetas y señales en palabras", async () => {
    renderPage();

    expect(await screen.findByTestId("candidate-left")).toHaveTextContent(
      "Ana Prueba Uno",
    );
    expect(screen.getByTestId("candidate-right")).toHaveTextContent(
      "Ana Prueba",
    );
    expect(
      screen.getByText("Un apellido de más o de menos entre los nombres"),
    ).toBeInTheDocument();
    // `score` llega como entero 0-100 (rapidfuzz), no como ratio 0-1 — no
    // debe mostrarse "9200%".
    expect(screen.getByText("Similitud: 92%")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Es la misma persona/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Son personas distintas/i }),
    ).toBeInTheDocument();
  });

  it("chip de advertencia cuando hay un deportista enlazado involucrado", async () => {
    mswServer.use(
      http.get("*/api/race-identity/candidates", () =>
        HttpResponse.json(
          makeCandidatesResponse({
            items: [
              makeIdentityCandidate({ id: 9, linked_athlete_involved: true }),
            ],
            total: 1,
          }),
        ),
      ),
    );
    renderPage();
    expect(await screen.findByTestId("linked-athlete-chip")).toHaveTextContent(
      "Incluye un deportista enlazado",
    );
  });

  it("resume: el progreso refleja lo ya decidido (2 de 3)", async () => {
    mswServer.use(
      http.get("*/api/race-identity/summary", () =>
        HttpResponse.json(makeSummaryResponse({ pending: 1, same_person: 2 })),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("review-progress")).toHaveTextContent(
        "2 de 3 decididos",
      );
    });
  });

  it("vacío: sin candidatos pendientes muestra el mensaje correspondiente", async () => {
    mswServer.use(raceIdentityEmptyHandler, raceIdentityEmptySummaryHandler);
    renderPage();
    expect(
      await screen.findByText("No hay candidatos pendientes de revisión."),
    ).toBeInTheDocument();
    expect(await screen.findByTestId("review-progress")).toHaveTextContent(
      "Sin candidatos por revisar",
    );
  });

  it("error: falla la carga y ofrece reintentar", async () => {
    mswServer.use(raceIdentityErrorHandler);
    renderPage();
    expect(
      await screen.findByText(
        "No se pudo cargar la revisión de identidad.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Reintentar/i }),
    ).toBeInTheDocument();
  });

  it("decide 'misma persona' y muestra el toast de éxito", async () => {
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("decide-same-person");
    await user.click(button);
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Registrado: es la misma persona.",
      );
    });
  });

  it("recalcular informa los candidatos retirados por no involucrar al club", async () => {
    mswServer.use(
      http.post("*/api/race-identity/rebuild", () =>
        HttpResponse.json({
          created: 0,
          unchanged: 1,
          pending: 1,
          removed: 3,
          imports_unreadable: [],
        }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByTestId("rebuild-candidates"));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Candidatos recalculados: 0 nuevos, 1 pendientes. 3 sin atletas del club se retiraron de la cola.",
      );
    });
  });

  it("409 al decidir: muestra el toast de error específico", async () => {
    mswServer.use(raceIdentityDecideConflictHandler);
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("decide-same-person");
    await user.click(button);
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Este candidato ya fue decidido.",
      );
    });
  });

  it("409 linked_competitor_ambiguous al decidir: muestra el mensaje específico del backend", async () => {
    mswServer.use(raceIdentityDecideLinkedAmbiguousHandler);
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("decide-same-person");
    await user.click(button);
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Este competidor está vinculado a un deportista del club. Desvincúlalo, decide y vuelve a vincularlo.",
      );
    });
  });

  it("atajo de teclado '1' decide 'misma persona'", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("decide-same-person");
    await user.keyboard("1");
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Registrado: es la misma persona.",
      );
    });
  });

  it("atajo de teclado '2' decide 'personas distintas'", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("decide-same-person");
    await user.keyboard("2");
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Registrado: son personas distintas.",
      );
    });
  });

  it("un segundo '1' disparado mientras la cola todavía refresca no dispara un segundo decide (ux-review.md MAJOR #2)", async () => {
    let decideCalls = 0;
    let candidatesCalls = 0;

    mswServer.use(
      http.get("*/api/race-identity/candidates", async () => {
        candidatesCalls += 1;
        // La primera carga responde al toque; el refetch disparado por la
        // invalidación del decide (2da llamada en adelante) tarda — esa es
        // la ventana en la que `candidatesQuery.isFetching` debe seguir
        // bloqueando un segundo atajo de teclado.
        if (candidatesCalls > 1) {
          await delay(60);
        }
        return HttpResponse.json(makeCandidatesResponse());
      }),
      http.post(
        "*/api/race-identity/candidates/:id/decide",
        async ({ params }) => {
          decideCalls += 1;
          return HttpResponse.json({
            id: Number(params.id),
            state: "same_person",
            merged: false,
            results_moved: 0,
          });
        },
      ),
    );

    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("decide-same-person");

    // Dos atajos disparados de inmediato, uno tras otro — el segundo cae
    // dentro de la ventana en la que `candidatesQuery.isFetching` sigue en
    // `true` (el refetch invalidado por el primer decide tarda 60ms).
    await user.keyboard("1");
    await user.keyboard("1");

    // Deja que el refetch (60ms) termine y la pantalla vuelva a estar lista.
    await waitFor(
      () => {
        expect(candidatesCalls).toBeGreaterThan(1);
      },
      { timeout: 1000 },
    );
    await new Promise((resolve) => setTimeout(resolve, 100));

    // El segundo atajo nunca debió llegar a decidir — solo una llamada real
    // al backend, sin importar cuántas veces se presionó "1" mientras la
    // pantalla seguía mostrando el par recién decidido.
    expect(decideCalls).toBe(1);
  });

  it("deshacer: filtro 'misma persona' muestra Deshacer y pide confirmación", async () => {
    mswServer.use(
      http.get("*/api/race-identity/candidates", () =>
        HttpResponse.json(
          makeCandidatesResponse({
            items: [
              makeIdentityCandidate({ id: 5, state: "same_person" }),
            ],
            total: 1,
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("combobox", { name: /Filtrar por estado/i }));
    await user.click(
      await screen.findByRole("option", { name: /Decididos: misma persona/i }),
    );

    const undoButton = await screen.findByTestId("undo-5");
    await user.click(undoButton);

    expect(
      await screen.findByText("¿Deshacer esta decisión?"),
    ).toBeInTheDocument();

    const confirmButton = screen.getByTestId("confirm-undo");
    await user.click(confirmButton);

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Decisión deshecha. El candidato vuelve a pendiente.",
      );
    });
  });

  it("sin violaciones de accesibilidad en la página (modo pendientes)", async () => {
    const { container } = renderPage();
    await screen.findByTestId("decide-same-person");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones de accesibilidad en el diálogo de confirmación de deshacer", async () => {
    mswServer.use(
      http.get("*/api/race-identity/candidates", () =>
        HttpResponse.json(
          makeCandidatesResponse({
            items: [
              makeIdentityCandidate({ id: 5, state: "same_person" }),
            ],
            total: 1,
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    const { container } = renderPage();

    await user.click(screen.getByRole("combobox", { name: /Filtrar por estado/i }));
    await user.click(
      await screen.findByRole("option", { name: /Decididos: misma persona/i }),
    );
    await user.click(await screen.findByTestId("undo-5"));
    await screen.findByText("¿Deshacer esta decisión?");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
