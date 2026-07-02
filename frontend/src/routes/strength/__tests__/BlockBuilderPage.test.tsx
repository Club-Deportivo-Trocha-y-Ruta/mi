/**
 * Tests para BlockBuilderPage (US2 / T027) — flujo de adjuntar un bloque
 * guardado a una sesión de entrenamiento existente:
 *   - Antes de guardar el bloque, la sección "Adjuntar a una sesión" no se
 *     renderiza (savedBlockId es null).
 *   - Tras guardar un bloque nuevo con éxito, aparece el selector de
 *     sesiones (radiogroup) con las sesiones existentes del club.
 *   - Buscar filtra las sesiones por fecha/lugar/foco técnico.
 *   - Sin selección, el botón "Adjuntar a la sesión seleccionada" está
 *     deshabilitado.
 *   - Seleccionar una sesión y adjuntar exitosamente muestra la confirmación
 *     con enlace "Ver sesión".
 *   - Error al adjuntar muestra una alerta inline sin perder la selección.
 *   - jest-axe sin violaciones en el estado inicial (modo creación) y en el
 *     flujo de adjunto tras guardar.
 *
 * Estrategia: MSW real vía mswServer.use(...strengthHandlers) + handler
 * custom para /api/training-sessions con datos distinguibles (evita
 * ambigüedad de accessible name entre las dos sesiones fixture por defecto
 * de trainingHandlers, que comparten fecha/lugar/foco). useAuthStore se
 * mockea para inyectar un accessToken determinista (requerido por
 * useTrainingSessions) sin levantar el stack de auth real.
 *
 * Mirror de `components/technique/__tests__/CatalogPage.test.tsx` para el
 * patrón de mock de useAuthStore + MSW.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { http, HttpResponse } from "msw";

import { BlockBuilderPage } from "@/routes/strength/BlockBuilderPage";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  strengthHandlers,
  strengthAttachErrorHandler,
} from "@/test/msw/strengthHandlers";
import { makeSession } from "@/test/msw/trainingHandlers";
import { UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mock del store de autenticación
// ---------------------------------------------------------------------------

const mockCoachUser = {
  id: 10,
  email: "entrenador@trochyruta.com",
  full_name: "Entrenador Ficticio",
  role: UserRole.coach,
  club_id: 1,
};

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: {
      user: typeof mockCoachUser;
      accessToken: string;
    }) => unknown,
  ) => selector({ user: mockCoachUser, accessToken: "fixture-token-ficticio" }),
}));

// ---------------------------------------------------------------------------
// Fixtures — sesiones distinguibles por lugar (evita nombres accesibles duplicados)
// ---------------------------------------------------------------------------

const SESSION_A = makeSession({
  id: 1,
  scheduled_date: "2026-05-15",
  location: "Cancha Ficticia A",
  technical_focus: "Frenada controlada",
});

const SESSION_B = makeSession({
  id: 2,
  scheduled_date: "2026-06-01",
  location: "Cancha Ficticia B",
  technical_focus: "Equilibrio",
});

const trainingSessionsHandler = http.get("*/api/training-sessions", () =>
  HttpResponse.json([SESSION_A, SESSION_B]),
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return renderWithProviders(<BlockBuilderPage />, {
    initialEntries: ["/strength/blocks/new"],
  });
}

async function saveBlock(user: ReturnType<typeof userEvent.setup>) {
  const nameInput = await screen.findByLabelText("Nombre del bloque");
  await user.type(nameInput, "Bloque ficticio");

  const select = screen.getByLabelText(
    "Agregar ejercicio al bloque",
  ) as HTMLSelectElement;
  await user.selectOptions(select, "Sentadilla con peso corporal");
  await user.click(screen.getByRole("button", { name: "Agregar" }));

  await user.click(screen.getByRole("button", { name: "Guardar bloque de fuerza" }));

  await waitFor(() => {
    expect(
      screen.getByRole("heading", { name: "Adjuntar a una sesión de entrenamiento" }),
    ).toBeInTheDocument();
  });
}

beforeEach(() => {
  mswServer.use(...strengthHandlers, trainingSessionsHandler);
});

// ---------------------------------------------------------------------------
// Suite: antes de guardar
// ---------------------------------------------------------------------------

describe("BlockBuilderPage — antes de guardar el bloque", () => {
  it("no muestra la sección de adjuntar a sesión", () => {
    renderPage();
    expect(
      screen.queryByRole("heading", { name: "Adjuntar a una sesión de entrenamiento" }),
    ).not.toBeInTheDocument();
  });

  it("renderiza el encabezado de modo creación", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Armar bloque de fuerza" }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: flujo de adjunto tras guardar
// ---------------------------------------------------------------------------

describe("BlockBuilderPage — flujo de adjuntar bloque a sesión", () => {
  it("tras guardar el bloque, aparece el selector de sesiones con las sesiones del club", async () => {
    const user = userEvent.setup();
    renderPage();

    await saveBlock(user);

    const radiogroup = await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });
    expect(within(radiogroup).getByText(/Cancha Ficticia A/)).toBeInTheDocument();
    expect(within(radiogroup).getByText(/Cancha Ficticia B/)).toBeInTheDocument();
  });

  it("el botón de adjuntar está deshabilitado sin sesión seleccionada", async () => {
    const user = userEvent.setup();
    renderPage();

    await saveBlock(user);
    await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });

    expect(
      screen.getByRole("button", { name: "Adjuntar a la sesión seleccionada" }),
    ).toBeDisabled();
  });

  it("buscar filtra las sesiones por lugar", async () => {
    const user = userEvent.setup();
    renderPage();

    await saveBlock(user);
    await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });

    await user.type(
      screen.getByLabelText("Buscar sesión de entrenamiento"),
      "Ficticia B",
    );

    await waitFor(() => {
      expect(screen.queryByText(/Cancha Ficticia A/)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Cancha Ficticia B/)).toBeInTheDocument();
  });

  it("seleccionar una sesión y adjuntar muestra la confirmación con enlace 'Ver sesión'", async () => {
    const user = userEvent.setup();
    renderPage();

    await saveBlock(user);
    await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });

    await user.click(screen.getByText(/Cancha Ficticia A/));
    await user.click(
      screen.getByRole("button", { name: "Adjuntar a la sesión seleccionada" }),
    );

    await waitFor(() => {
      expect(
        screen.getByText("Bloque adjuntado correctamente"),
      ).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: "Ver sesión" });
    expect(link).toHaveAttribute("href", "/training/sessions/1");
  });

  it("muestra una alerta inline si el adjunto falla, sin perder el flujo", async () => {
    mswServer.use(strengthAttachErrorHandler);

    const user = userEvent.setup();
    renderPage();

    await saveBlock(user);
    await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });

    await user.click(screen.getByText(/Cancha Ficticia A/));
    await user.click(
      screen.getByRole("button", { name: "Adjuntar a la sesión seleccionada" }),
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Bloque adjuntado correctamente"),
    ).not.toBeInTheDocument();
    // El selector sigue disponible para reintentar
    expect(
      screen.getByRole("button", { name: "Adjuntar a la sesión seleccionada" }),
    ).toBeInTheDocument();
  });

  it("el enlace 'crea una sesión nueva' apunta al asistente de sesiones existente", async () => {
    const user = userEvent.setup();
    renderPage();

    await saveBlock(user);

    const link = screen.getByRole("link", { name: "crea una sesión nueva" });
    expect(link).toHaveAttribute("href", "/training/sessions/new");
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("BlockBuilderPage — accesibilidad", () => {
  it("no tiene violaciones de a11y en el estado inicial (modo creación)", async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Armar bloque de fuerza" }),
      ).toBeInTheDocument();
    });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y tras guardar el bloque y con el selector de sesiones visible", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();

    await saveBlock(user);
    await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en el estado de confirmación de adjunto", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();

    await saveBlock(user);
    await screen.findByRole("radiogroup", {
      name: "Sesiones de entrenamiento disponibles",
    });
    await user.click(screen.getByText(/Cancha Ficticia A/));
    await user.click(
      screen.getByRole("button", { name: "Adjuntar a la sesión seleccionada" }),
    );

    await waitFor(() => {
      expect(
        screen.getByText("Bloque adjuntado correctamente"),
      ).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
