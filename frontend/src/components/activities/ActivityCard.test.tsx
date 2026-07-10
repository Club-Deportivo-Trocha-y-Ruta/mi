/**
 * Tests de ActivityCard — gating de la acción "Enlazar a sesión" (feature
 * 025, T032b).
 *
 * Cierra el gap de integración: `LinkSessionDialog` existía pero nada la
 * renderizaba. Cubre la matriz doble de gating (`canLink` prop AND rol
 * coach/admin) y que el clic abre `LinkSessionDialog` con la actividad
 * correcta.
 *
 * Estrategia: mismo patrón que `LinkSessionDialog.test.tsx` — MSW contra la
 * capa HTTP real (`useSessionSuggestions`/`useTrainingSessions` NO se
 * mockean), `@/store/auth.store` mockeado con un rol mutable (`vi.hoisted`)
 * para poder alternar coach/parent entre tests del mismo archivo.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { mswServer } from "@/test/setup";
import { stravaHandlers, mockActivity } from "@/test/msw/stravaHandlers";
import { UserRole } from "@/types/enums";

// `vi.hoisted` corre antes de que los imports se resuelvan — usa el valor
// string literal ("coach") en vez de `UserRole.coach` para evitar un
// ReferenceError de inicialización circular con el import de más abajo.
const authState = vi.hoisted(() => ({
  role: "coach" as string | undefined,
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { accessToken: string; user: { id: number; role: string | undefined } }) => unknown,
  ) => selector({ accessToken: "test-token", user: { id: 1, role: authState.role } }),
}));

import { ActivityCard } from "./ActivityCard";

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
  authState.role = UserRole.coach;
  mswServer.use(...stravaHandlers);
});

// ---------------------------------------------------------------------------
// Gating: canLink + rol
// ---------------------------------------------------------------------------

describe("ActivityCard — gating de la acción de enlace", () => {
  it("coach + canLink: muestra 'Enlazar a sesión' en una actividad sin enlazar", () => {
    authState.role = UserRole.coach;
    wrap(<ActivityCard activity={unlinkedActivity} canLink />);

    expect(
      screen.getByRole("button", { name: /enlazar a sesión/i }),
    ).toBeInTheDocument();
  });

  it("coach + canLink: muestra 'Cambiar sesión' en una actividad ya enlazada", () => {
    authState.role = UserRole.coach;
    wrap(<ActivityCard activity={linkedActivity} canLink />);

    expect(
      screen.getByRole("button", { name: /cambiar sesión/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /enlazar a sesión/i }),
    ).not.toBeInTheDocument();
  });

  it("admin + canLink: también ve el botón", () => {
    authState.role = UserRole.admin;
    wrap(<ActivityCard activity={unlinkedActivity} canLink />);

    expect(
      screen.getByRole("button", { name: /enlazar a sesión/i }),
    ).toBeInTheDocument();
  });

  it("coach SIN canLink: no muestra el botón (la página no habilitó la acción)", () => {
    authState.role = UserRole.coach;
    wrap(<ActivityCard activity={unlinkedActivity} />);

    expect(
      screen.queryByRole("button", { name: /enlazar a sesión/i }),
    ).not.toBeInTheDocument();
  });

  it("padre con canLink=true de todas formas NO ve el botón (gate por rol)", () => {
    authState.role = UserRole.parent;
    wrap(<ActivityCard activity={unlinkedActivity} canLink />);

    expect(
      screen.queryByRole("button", { name: /enlazar a sesión/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /cambiar sesión/i }),
    ).not.toBeInTheDocument();
  });

  it("atleta con canLink=true de todas formas NO ve el botón (gate por rol)", () => {
    authState.role = UserRole.athlete;
    wrap(<ActivityCard activity={unlinkedActivity} canLink />);

    expect(
      screen.queryByRole("button", { name: /enlazar a sesión/i }),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Abre LinkSessionDialog
// ---------------------------------------------------------------------------

describe("ActivityCard — abre LinkSessionDialog", () => {
  it("un clic en 'Enlazar a sesión' abre el diálogo para esa actividad", async () => {
    authState.role = UserRole.coach;
    const user = userEvent.setup();
    wrap(<ActivityCard activity={unlinkedActivity} canLink />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /enlazar a sesión/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Vincular a sesión/i)).toBeInTheDocument();
    expect(await screen.findByText(/Pista XCO La Cumbre/)).toBeInTheDocument();
  });

  it("un clic en 'Cambiar sesión' abre el diálogo pre-seleccionando la sesión actual", async () => {
    authState.role = UserRole.coach;
    const user = userEvent.setup();
    wrap(<ActivityCard activity={linkedActivity} canLink />);

    await user.click(screen.getByRole("button", { name: /cambiar sesión/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Editar vínculo de sesión/i)).toBeInTheDocument();
  });
});
