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
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { CatalogPage } from "@/routes/technique/CatalogPage";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  techniqueHandlers,
  techniqueEmptyCatalogHandler,
  techniqueColdStartHandler,
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

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: typeof mockCoachUser }) => unknown) =>
    selector({ user: mockCoachUser }),
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

  it("muestra role=alert cuando la API falla", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("muestra copy de servidor iniciando para errores de red (MSW.error)", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
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
