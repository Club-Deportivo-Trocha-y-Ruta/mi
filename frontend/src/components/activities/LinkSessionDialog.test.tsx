/**
 * Tests de LinkSessionDialog (feature 025, T034).
 *
 * Cubre: selección de una sugerencia + vinculación (flujo feliz de SC-005),
 * desvinculación de la sesión actual, estado de error inline (sin cierre
 * silencioso del diálogo), búsqueda en el calendario como fallback, y
 * accesibilidad (0 violaciones axe) en ambos modos (sin enlazar / ya
 * enlazada).
 *
 * Estrategia: MSW contra la capa HTTP real (`useSessionSuggestions`,
 * `useTrainingSessions`, `useLinkActivity` NO se mockean) — mismo patrón que
 * `useStravaConnection.test.ts`. `@/store/auth.store` se mockea solo para
 * satisfacer el guard `enabled: !!accessToken` de `useTrainingSessions`
 * (patrón de `EditResultNoteDialog.test.tsx`). Timers reales para el
 * `setTimeout(900)` de auto-cierre — `waitFor` con timeout extendido, sin
 * `vi.useFakeTimers()` (consistente con el resto del módulo de diálogos).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";
import type { ReactElement } from "react";

import { mswServer } from "@/test/setup";
import {
  stravaHandlers,
  mockActivity,
  emptySessionSuggestionsHandler,
  linkActivityErrorHandler,
} from "@/test/msw/stravaHandlers";
import { makeSession } from "@/test/msw/trainingHandlers";

expect.extend(toHaveNoViolations);

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string; user: { id: number } }) => unknown) =>
    selector({ accessToken: "test-token", user: { id: 1 } }),
}));

import { LinkSessionDialog } from "./LinkSessionDialog";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrap(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const unlinkedActivity = mockActivity({ id: 5, link: null });

const linkedActivity = mockActivity({
  id: 5,
  link: {
    training_session_id: 10,
    session_label: "8 jul · Entrenamiento",
    linked_by: "Entrenador Ficticio",
    linked_at: "2026-07-08T12:00:00Z",
  },
});

beforeEach(() => {
  mswServer.use(...stravaHandlers);
});

// ---------------------------------------------------------------------------
// Sugerencias
// ---------------------------------------------------------------------------

describe("LinkSessionDialog — sugerencias de sesión", () => {
  it("carga y muestra las sesiones sugeridas por el backend", async () => {
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={vi.fn()} />);

    expect(await screen.findByText(/Pista XCO La Cumbre/)).toBeInTheDocument();
    expect(screen.getByText(/Parque El Ingenio/)).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it("muestra un mensaje claro cuando no hay sesiones cercanas", async () => {
    mswServer.use(emptySessionSuggestionsHandler);
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={vi.fn()} />);

    expect(
      await screen.findByText(/No hay sesiones cercanas a esta actividad/i),
    ).toBeInTheDocument();
  });

  it("el botón Vincular permanece deshabilitado hasta elegir una sesión", async () => {
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={vi.fn()} />);

    await screen.findAllByRole("radio");
    expect(screen.getByRole("button", { name: /^Vincular$/i })).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Selección de sugerencia → vincular (flujo feliz)
// ---------------------------------------------------------------------------

describe("LinkSessionDialog — vincula al elegir una sugerencia", () => {
  it("envía el training_session_id elegido y muestra confirmación", async () => {
    const linkedIds: (number | null)[] = [];
    mswServer.use(
      http.patch("*/api/activities/:id/link", async ({ request, params }) => {
        const body = (await request.json()) as { training_session_id: number | null };
        linkedIds.push(body.training_session_id);
        return HttpResponse.json(
          mockActivity({ id: Number(params.id), link: null }),
        );
      }),
    );

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={onOpenChange} />);

    const radios = await screen.findAllByRole("radio");
    await user.click(radios[0]);
    await user.click(screen.getByRole("button", { name: /^Vincular$/i }));

    await waitFor(() => expect(linkedIds).toEqual([10]));
    expect(
      await screen.findByText(/Actividad vinculada correctamente/i),
    ).toBeInTheDocument();

    // Auto-cierre tras confirmación (setTimeout real de 900ms en el componente).
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false), {
      timeout: 3_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Desvincular
// ---------------------------------------------------------------------------

describe("LinkSessionDialog — desvincula la sesión actual", () => {
  it("envía training_session_id=null y confirma la desvinculación", async () => {
    const linkedIds: (number | null)[] = [];
    mswServer.use(
      http.patch("*/api/activities/:id/link", async ({ request }) => {
        const body = (await request.json()) as { training_session_id: number | null };
        linkedIds.push(body.training_session_id);
        return HttpResponse.json(mockActivity({ id: 5, link: null }));
      }),
    );

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    wrap(<LinkSessionDialog activity={linkedActivity} open onOpenChange={onOpenChange} />);

    const unlinkButton = await screen.findByRole("button", { name: /desvincular/i });
    await user.click(unlinkButton);

    await waitFor(() => expect(linkedIds).toEqual([null]));
    expect(await screen.findByText(/Actividad desvinculada/i)).toBeInTheDocument();

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false), {
      timeout: 3_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Estado de error
// ---------------------------------------------------------------------------

describe("LinkSessionDialog — estado de error", () => {
  it("muestra un error inline y NO cierra el diálogo cuando falla el enlace", async () => {
    mswServer.use(linkActivityErrorHandler);

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={onOpenChange} />);

    const radios = await screen.findAllByRole("radio");
    await user.click(radios[0]);
    await user.click(screen.getByRole("button", { name: /^Vincular$/i }));

    const errorToast = await screen.findByRole("status");
    expect(errorToast).toHaveTextContent(/No se pudo actualizar el vínculo/i);
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("muestra un error inline y NO cierra el diálogo cuando falla la desvinculación", async () => {
    mswServer.use(linkActivityErrorHandler);

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    wrap(<LinkSessionDialog activity={linkedActivity} open onOpenChange={onOpenChange} />);

    const unlinkButton = await screen.findByRole("button", { name: /desvincular/i });
    await user.click(unlinkButton);

    const errorToast = await screen.findByRole("status");
    expect(errorToast).toHaveTextContent(/No se pudo actualizar el vínculo/i);
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

// ---------------------------------------------------------------------------
// Búsqueda en el calendario (fallback)
// ---------------------------------------------------------------------------

describe("LinkSessionDialog — búsqueda en el calendario", () => {
  it("filtra los resultados de calendario por texto libre", async () => {
    mswServer.use(
      http.get("*/api/training-sessions", () =>
        HttpResponse.json([
          makeSession({
            id: 101,
            location: "Pista XCO La Cumbre",
            technical_focus: "Frenada controlada",
          }),
          makeSession({
            id: 102,
            location: "Velódromo Alberto Galindo",
            technical_focus: "Resistencia aeróbica",
          }),
        ]),
      ),
    );

    const user = userEvent.setup();
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={vi.fn()} />);

    await screen.findAllByRole("radio");

    const toggle = screen.getByRole("button", {
      name: /buscar en el calendario/i,
    });
    await user.click(toggle);

    const searchInput = await screen.findByRole("searchbox", {
      name: /buscar sesión en el calendario/i,
    });
    await user.type(searchInput, "Velódromo");

    const searchSection = document.getElementById(
      "link-session-calendar-search",
    ) as HTMLElement;

    await waitFor(() => {
      expect(within(searchSection).getByText(/Velódromo Alberto Galindo/)).toBeInTheDocument();
      expect(within(searchSection).queryByText(/^Pista XCO La Cumbre/)).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("LinkSessionDialog — accesibilidad", () => {
  it("no tiene violaciones de accesibilidad con sugerencias cargadas (actividad sin enlazar)", async () => {
    wrap(<LinkSessionDialog activity={unlinkedActivity} open onOpenChange={vi.fn()} />);

    await screen.findAllByRole("radio");

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("no tiene violaciones de accesibilidad con la sección Desvincular visible (actividad ya enlazada)", async () => {
    wrap(<LinkSessionDialog activity={linkedActivity} open onOpenChange={vi.fn()} />);

    await screen.findByRole("button", { name: /desvincular/i });

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
