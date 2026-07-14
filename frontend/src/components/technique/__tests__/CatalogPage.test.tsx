/**
 * Tests de integración para CatalogPage (US1):
 *   Compone FilterBar + CatalogGrid + ExerciseFormDialog.
 *   Role coach — ve catálogo, puede crear ejercicios.
 *   Estados: loading, error (cold-start), empty sin filtros, empty con filtros,
 *   success con datos, botón "Nuevo ejercicio" visible solo para coach/admin.
 *
 * Estrategia de mock:
 *   - useAuthStore se mockea con vi.mock para inyectar el rol coach de forma
 *     determinista (sigue el patrón de otros tests del proyecto que deben
 *     controlar la sesión sin levantar un stack de auth real).
 *   - useTechniqueCatalog, useSkills, useMaterials se resuelven via MSW
 *     (mswServer.use(techniqueHandlers) en beforeEach).
 *   - ExerciseFormDialog se mockea con vi.mock para evitar dependencias
 *     profundas del formulario de creación (fuera del scope de esta suite).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { CatalogPage } from "@/routes/technique/CatalogPage";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  techniqueHandlers,
  techniqueEmptyCatalogHandler,
  techniqueColdStartHandler,
  createStatefulSessionExercisesHandlers,
} from "@/test/msw/techniqueHandlers";
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

// `accessToken` se incluye porque SessionPickerDialog (T017) consume
// useTrainingSessions, que solo dispara su query cuando hay un token —
// sin esto el picker queda cargando para siempre (feature 032).
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: {
      user: typeof mockCoachUser;
      accessToken: string;
    }) => unknown,
  ) => selector({ user: mockCoachUser, accessToken: "test-access-token" }),
}));

// ---------------------------------------------------------------------------
// Mock del dialog de creación/edición
// (la lógica del formulario se prueba en su propia suite — aquí solo
//  verificamos que CatalogPage lo abre y cierra correctamente)
// ---------------------------------------------------------------------------

vi.mock("@/components/technique/ExerciseFormDialog", () => ({
  ExerciseFormDialog: ({
    open,
    onOpenChange,
  }: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
  }) =>
    open ? (
      <div role="dialog" aria-label="Formulario de ejercicio">
        <button onClick={() => onOpenChange(false)}>Cerrar formulario</button>
      </div>
    ) : null,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return renderWithProviders(<CatalogPage />);
}

// ---------------------------------------------------------------------------
// Suite: encabezado y estructura de página
// ---------------------------------------------------------------------------

describe("CatalogPage — encabezado", () => {
  beforeEach(() => {
    mswServer.use(...techniqueHandlers);
  });

  it("renderiza el título de la página", async () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: /Biblioteca de técnica y gymkhana/ }),
    ).toBeInTheDocument();
  });

  it("renderiza el subtítulo descriptivo", async () => {
    renderPage();
    expect(
      screen.getByText(/Explora y filtra los ejercicios técnicos/),
    ).toBeInTheDocument();
  });

  it("el coach ve el botón 'Nuevo ejercicio'", async () => {
    renderPage();
    expect(
      screen.getByRole("button", { name: /Crear nuevo ejercicio en el catálogo/ }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado de carga
// ---------------------------------------------------------------------------

describe("CatalogPage — estado de carga", () => {
  beforeEach(() => {
    mswServer.use(...techniqueHandlers);
  });

  it("muestra el estado de carga del grid mientras se resuelve la query", () => {
    renderPage();
    // The grid loading skeleton appears before the query resolves.
    const gridStatus = screen.getByRole("status", {
      name: "Cargando catálogo de ejercicios…",
    });
    expect(gridStatus).toBeInTheDocument();
    expect(gridStatus).toHaveAttribute("aria-busy", "true");
  });

  it("el estado de carga desaparece una vez que se reciben los datos", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado de error / cold-start
// ---------------------------------------------------------------------------

describe("CatalogPage — estado de error", () => {
  beforeEach(() => {
    mswServer.use(techniqueColdStartHandler, ...techniqueHandlers);
  });

  it("muestra role=status (cold-start, no alert) cuando la API falla por red", async () => {
    // techniqueColdStartHandler simulates a network error — the shared
    // `ErrorState` renders that as role="status" (reassuring tone), not
    // role="alert" (feature 033 / T041).
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  it("muestra copy de servidor iniciando para errores de red (MSW.error)", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        /El servidor está iniciando/,
      );
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: catálogo vacío (sin filtros)
// ---------------------------------------------------------------------------

describe("CatalogPage — catálogo vacío sin filtros", () => {
  beforeEach(() => {
    mswServer.use(techniqueEmptyCatalogHandler, ...techniqueHandlers);
  });

  it("muestra el estado vacío por defecto cuando no hay ejercicios ni filtros", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("El catálogo está vacío")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Aún no hay ejercicios registrados en esta biblioteca."),
    ).toBeInTheDocument();
  });

  it("no muestra 'Sin resultados para estos filtros' sin filtros activos", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("El catálogo está vacío")).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Sin resultados para estos filtros"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: catálogo vacío con filtros activos
// ---------------------------------------------------------------------------

describe("CatalogPage — catálogo vacío con filtros", () => {
  beforeEach(() => {
    mswServer.use(techniqueEmptyCatalogHandler, ...techniqueHandlers);
  });

  it("muestra 'Sin resultados para estos filtros' tras aplicar un filtro", async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for filter bar materials to load so the component is interactive
    await waitFor(() =>
      expect(screen.getByLabelText("Dificultad")).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByLabelText("Dificultad"), "avanzada");

    await waitFor(() => {
      expect(
        screen.getByText("Sin resultados para estos filtros"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText("Ajusta o limpia los filtros para ver más ejercicios."),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado exitoso con datos
// ---------------------------------------------------------------------------

describe("CatalogPage — estado exitoso", () => {
  beforeEach(() => {
    mswServer.use(...techniqueHandlers);
  });

  it("renderiza las tarjetas de ejercicios recibidas de la API", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });
    expect(screen.getByText("Gymkhana básica")).toBeInTheDocument();
  });

  it("cada tarjeta tiene botón de edición (coach)", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });
    const editButtons = screen.getAllByRole("button", { name: /Editar ejercicio/ });
    expect(editButtons.length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Suite: interacción con el dialog
// ---------------------------------------------------------------------------

describe("CatalogPage — dialog de creación", () => {
  beforeEach(() => {
    mswServer.use(...techniqueHandlers);
  });

  it("abre el dialog al hacer clic en 'Nuevo ejercicio'", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      screen.getByRole("button", { name: /Crear nuevo ejercicio en el catálogo/ }),
    );

    expect(screen.getByRole("dialog", { name: "Formulario de ejercicio" })).toBeInTheDocument();
  });

  it("cierra el dialog al hacer clic en 'Cerrar formulario'", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      screen.getByRole("button", { name: /Crear nuevo ejercicio en el catálogo/ }),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cerrar formulario" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("abre el dialog en modo edición al clicar el botón de editar una tarjeta", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    const editButtons = screen.getAllByRole("button", { name: /Editar ejercicio/ });
    await user.click(editButtons[0]);

    expect(screen.getByRole("dialog", { name: "Formulario de ejercicio" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: "Adjuntar a una sesión" — entry point de biblioteca (feature 032, T013)
//
// GET /api/training-sessions ya está mockeado globalmente por trainingHandlers
// (src/test/setup.ts) — devuelve dos sesiones "planned"/"executed" con id 1/2,
// la primera en "Pista XCO La Cumbre". No hace falta un handler adicional
// para el picker; solo agregamos el par GET/POST stateful de
// /api/technique/sessions/:id/exercises para el adjunto en sí.
// ---------------------------------------------------------------------------

describe("CatalogPage — adjuntar a una sesión", () => {
  beforeEach(() => {
    const sessionExercises = createStatefulSessionExercisesHandlers(1);
    mswServer.use(...techniqueHandlers, ...sessionExercises.handlers);
  });

  it("abre SessionPickerDialog al hacer clic en 'Adjuntar a una sesión' de una tarjeta", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: "Adjuntar Slalom con conos a una sesión" }),
    );

    expect(screen.getByRole("dialog", { name: "¿A qué sesión?" })).toBeInTheDocument();
  });

  it("al elegir una sesión, adjunta directamente (sin navegar) y muestra 'Ver en la sesión'", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: "Adjuntar Slalom con conos a una sesión" }),
    );

    const dialog = screen.getByRole("dialog", { name: "¿A qué sesión?" });
    const sessionButton = within(dialog)
      .getAllByRole("button")
      .find((btn) => btn.textContent?.includes("Pista XCO La Cumbre"));
    expect(sessionButton).toBeDefined();
    await user.click(sessionButton!);

    // El diálogo se cierra — no hay navegación, seguimos en CatalogPage.
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "¿A qué sesión?" })).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("heading", { name: /Biblioteca de técnica y gymkhana/ }),
    ).toBeInTheDocument();

    // Enlace "Ver en la sesión" hacia la sección Plan de la sesión elegida.
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Ver en la sesión" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Ver en la sesión" })).toHaveAttribute(
      "href",
      "/training/sessions/1?section=plan",
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("CatalogPage — accesibilidad", () => {
  beforeEach(() => {
    mswServer.use(...techniqueHandlers);
  });

  it("no tiene violaciones de accesibilidad durante la carga del catálogo", async () => {
    const { container } = renderPage();
    // The CatalogGrid loading state (role="status" skeletons) must be axe-clean.
    // FilterBar materials skeleton now also uses role="status" (a11y fix in FilterBar).
    // We audit at mount time (before data resolves) to cover the loading skeleton.
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con el catálogo cargado", async () => {
    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
