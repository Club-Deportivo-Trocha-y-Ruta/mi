/**
 * Tests para BlockBuilderPage (feature 021 / T027 — flujo original de
 * adjunto; feature 032 / T011 — preselect `?session_id=` + resumen
 * bloqueado + auto-adjunto, US1):
 *
 *   - Con `?session_id=` presente (entry point 1 del contrato de adjunto
 *     unificado): la sesión se muestra como un resumen bloqueado de solo
 *     lectura (texto estático, no un `disabled` input) y el selector
 *     buscable de sesiones (`role="radiogroup"`) nunca se renderiza.
 *   - Guardar el bloque con sesión bloqueada dispara el adjunto
 *     automáticamente y navega a `/training/sessions/{id}?section=plan`
 *     — sin la elección manual "Ver sesión / Seguir editando" de antes.
 *   - `AgeBandGuardrailDialog` sigue abriéndose sin cambios desde este
 *     camino preseleccionado (SC-007, research.md R9) — el guardrail vive
 *     en la lógica de guardado del bloque, no tocada por esta feature.
 *   - Sin `?session_id=` (entry points 2/3): `SessionPickerDialog`
 *     aparece antes que el formulario de armado; el formulario no se
 *     renderiza hasta elegir una sesión. Elegir una sesión navega con
 *     `?session_id={id}` (replace).
 *
 * Estrategia: MSW real vía mswServer.use(...strengthHandlers, ...) +
 * handlers custom para `/api/training-sessions` con datos distinguibles.
 * `useAuthStore` se mockea para inyectar un accessToken determinista
 * (requerido por `useTrainingSession`/`useTrainingSessions`).
 * `useNavigate` se mockea (manteniendo el resto de react-router-dom real)
 * para poder aserir a qué ruta se navegó tras el auto-adjunto — mismo
 * patrón que `ImportWizard.postimport.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { http, HttpResponse } from "msw";

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  strengthHandlers,
  strengthAttachErrorHandler,
  strengthSaveBlockAgeBandGuardrailHandler,
} from "@/test/msw/strengthHandlers";
import { makeSession } from "@/test/msw/trainingHandlers";
import { UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de cualquier import dinámico
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

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

// `vi.mock` se hoistea automáticamente por encima de este import estático.
import { BlockBuilderPage } from "@/routes/strength/BlockBuilderPage";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Sesión bloqueada (`?session_id=1`) — coincide con `GET /training-sessions/:id`. */
const LOCKED_SESSION = makeSession({
  id: 1,
  scheduled_date: "2026-05-15",
  location: "Pista XCO La Cumbre",
  technical_focus: "Frenada controlada",
});
const LOCKED_SESSION_LABEL =
  "2026-05-15 — Pista XCO La Cumbre — Frenada controlada";

const trainingSessionByIdHandler = http.get(
  "*/api/training-sessions/:id",
  ({ params }) =>
    HttpResponse.json({ ...LOCKED_SESSION, id: Number(params.id) || 1 }),
);

/** Sesión ofrecida por SessionPickerDialog cuando no hay `?session_id=`. */
const SESSION_A = makeSession({
  id: 7,
  scheduled_date: "2026-06-01",
  location: "Cancha Ficticia A",
  technical_focus: "Equilibrio",
});

const trainingSessionsListHandler = http.get("*/api/training-sessions", () =>
  HttpResponse.json([SESSION_A]),
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLocked(sessionId: number | string = 1) {
  return renderWithProviders(<BlockBuilderPage />, {
    initialEntries: [`/strength/blocks/new?session_id=${sessionId}`],
  });
}

function renderNoSession() {
  return renderWithProviders(<BlockBuilderPage />, {
    initialEntries: ["/strength/blocks/new"],
  });
}

/** Llena el formulario mínimo y hace clic en "Guardar bloque de fuerza". */
async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  const nameInput = await screen.findByLabelText("Nombre del bloque");
  await user.type(nameInput, "Bloque ficticio");

  const select = screen.getByLabelText(
    "Agregar ejercicio al bloque",
  ) as HTMLSelectElement;
  await user.selectOptions(select, "Sentadilla con peso corporal");
  await user.click(screen.getByRole("button", { name: "Agregar" }));

  await user.click(
    screen.getByRole("button", { name: "Guardar bloque de fuerza" }),
  );
}

beforeEach(() => {
  mockNavigate.mockClear();
  mswServer.use(
    trainingSessionByIdHandler,
    trainingSessionsListHandler,
    ...strengthHandlers,
  );
});

// ---------------------------------------------------------------------------
// Suite: con ?session_id= — resumen bloqueado (T018, entry point 1)
// ---------------------------------------------------------------------------

describe("BlockBuilderPage — con ?session_id= (sesión conocida)", () => {
  it("renderiza el resumen de sesión bloqueado como texto estático, no un input", async () => {
    renderLocked();

    expect(
      await screen.findByText(LOCKED_SESSION_LABEL),
    ).toBeInTheDocument();
    // Convención feature 015: nunca un input `disabled`.
    expect(screen.queryByRole("textbox", { name: /sesión/i })).not.toBeInTheDocument();
  });

  it("no renderiza el selector buscable de sesiones (radiogroup)", async () => {
    renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Buscar sesión de entrenamiento"),
    ).not.toBeInTheDocument();
  });

  it("muestra el formulario de armado directamente, sin preguntar por la sesión", async () => {
    renderLocked();

    expect(
      await screen.findByRole("heading", { name: "Armar bloque de fuerza" }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Nombre del bloque"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it('ofrece "Cambiar sesión" antes de guardar, y lo oculta después de guardar', async () => {
    const user = userEvent.setup();
    renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);
    expect(
      screen.getByRole("link", { name: /Cambiar sesión/ }),
    ).toBeInTheDocument();

    await fillAndSubmit(user);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalled();
    });
  });

  it("guarda el bloque, adjunta automáticamente y navega a la sesión con section=plan (T019)", async () => {
    const user = userEvent.setup();
    renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/training/sessions/1?section=plan",
      );
    });
  });

  it("un 409 (ya adjunto) igual navega a la sesión — no es un error bloqueante", async () => {
    mswServer.use(
      http.post(
        "*/api/strength/blocks/:id/attach",
        () =>
          new HttpResponse(
            JSON.stringify({
              detail: "Este bloque ya está adjunto a esta sesión.",
            }),
            { status: 409 },
          ),
      ),
    );

    const user = userEvent.setup();
    renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/training/sessions/1?section=plan",
      );
    });
  });

  it("un error real de adjunto muestra una alerta con opción de reintentar, sin navegar", async () => {
    mswServer.use(strengthAttachErrorHandler);

    const user = userEvent.setup();
    renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);
    await fillAndSubmit(user);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Reintentar adjunto" }),
    ).toBeInTheDocument();
  });

  it("AgeBandGuardrailDialog sigue abriéndose sin cambios desde este camino preseleccionado (SC-007)", async () => {
    mswServer.use(strengthSaveBlockAgeBandGuardrailHandler);

    const user = userEvent.setup();
    renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);

    // `BlockAssembler` solo abre el diálogo si encuentra localmente una
    // entrada cuyo ejercicio no calza con `target_age_band` (mismo
    // algoritmo que el backend, `findFirstAgeBandViolation`) — "Sentadilla
    // con peso corporal" (age_bands: ["10-12"]) contra un objetivo "13-15"
    // produce esa violación real.
    const ageBandSelect = await screen.findByLabelText(
      "Franja de edad objetivo",
    );
    await user.selectOptions(ageBandSelect, "13-15");
    await fillAndSubmit(user);

    expect(
      await screen.findByRole("heading", {
        name: "Ejercicio fuera de la franja de edad",
      }),
    ).toBeInTheDocument();
    // El guardado no se completó — no hay adjunto ni navegación.
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: sin ?session_id= — se pregunta primero (T018, entry points 2/3)
// ---------------------------------------------------------------------------

describe("BlockBuilderPage — sin ?session_id= (sesión desconocida)", () => {
  it("muestra el selector de sesiones antes del formulario de armado", async () => {
    renderNoSession();

    expect(
      await screen.findByRole("dialog", {
        name: "¿A qué sesión vas a adjuntar el bloque?",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Nombre del bloque"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Armar bloque de fuerza" }),
    ).not.toBeInTheDocument();
  });

  it("al elegir una sesión, navega a /strength/blocks/new?session_id= con replace", async () => {
    const user = userEvent.setup();
    renderNoSession();

    const dialog = await screen.findByRole("dialog", {
      name: "¿A qué sesión vas a adjuntar el bloque?",
    });
    const sessionButton = await within(dialog).findByRole("button", {
      name: /Cancha Ficticia A/,
    });
    await user.click(sessionButton);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        "/strength/blocks/new?session_id=7",
        { replace: true },
      );
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("BlockBuilderPage — accesibilidad", () => {
  it("no tiene violaciones de a11y con la sesión bloqueada y el formulario visible", async () => {
    const { container } = renderLocked();

    await screen.findByText(LOCKED_SESSION_LABEL);
    await screen.findByRole("heading", { name: "Armar bloque de fuerza" });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con el selector de sesiones abierto (sin session_id)", async () => {
    const { container } = renderNoSession();

    await screen.findByRole("dialog", {
      name: "¿A qué sesión vas a adjuntar el bloque?",
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
