/**
 * Tests de integración para CatalogPage de Fuerza y Acondicionamiento (US1 / T018):
 *   Compone FilterBar + CatalogGrid vía useStrengthCatalog.
 *   Estados: loading, error (cold-start), empty sin filtros, empty con filtros,
 *   success con datos.
 *
 * Mirror de `components/technique/__tests__/CatalogPage.test.tsx` (feature 018),
 * sin mock de useAuthStore ni de un dialog de creación: el catálogo de fuerza
 * es curado estáticamente en v1 (no hay creación/edición desde la UI, ver
 * routes/strength/CatalogPage.tsx).
 *
 * Estrategia de mock: useStrengthCatalog se resuelve via MSW
 * (mswServer.use(strengthHandlers) en beforeEach).
 */
import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { CatalogPage } from "@/routes/strength/CatalogPage";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  strengthHandlers,
  strengthEmptyCatalogHandler,
  strengthColdStartHandler,
} from "@/test/msw/strengthHandlers";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return renderWithProviders(<CatalogPage />);
}

// ---------------------------------------------------------------------------
// Suite: encabezado
// ---------------------------------------------------------------------------

describe("CatalogPage (strength) — encabezado", () => {
  beforeEach(() => {
    mswServer.use(...strengthHandlers);
  });

  it("renderiza el título de la página", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: /Biblioteca de fuerza y acondicionamiento/ }),
    ).toBeInTheDocument();
  });

  it("renderiza el subtítulo descriptivo", () => {
    renderPage();
    expect(
      screen.getByText(/Explora y filtra ejercicios de fortalecimiento ilustrados/),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado de carga
// ---------------------------------------------------------------------------

describe("CatalogPage (strength) — estado de carga", () => {
  beforeEach(() => {
    mswServer.use(...strengthHandlers);
  });

  it("muestra el estado de carga del grid mientras se resuelve la query", () => {
    renderPage();
    const gridStatus = screen.getByRole("status", {
      name: "Cargando catálogo de ejercicios de fuerza…",
    });
    expect(gridStatus).toBeInTheDocument();
    expect(gridStatus).toHaveAttribute("aria-busy", "true");
  });

  it("el estado de carga desaparece una vez que se reciben los datos", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Sentadilla con peso corporal")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: estado de error / cold-start
// ---------------------------------------------------------------------------

describe("CatalogPage (strength) — estado de error", () => {
  beforeEach(() => {
    mswServer.use(strengthColdStartHandler, ...strengthHandlers);
  });

  it("muestra role=status (cold-start, no alert) cuando la API falla por red", async () => {
    // strengthColdStartHandler simulates a network error — the shared
    // `ErrorState` renders that as role="status" (reassuring tone), not
    // role="alert" (feature 033 / T042).
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

describe("CatalogPage (strength) — catálogo vacío sin filtros", () => {
  beforeEach(() => {
    mswServer.use(strengthEmptyCatalogHandler, ...strengthHandlers);
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

describe("CatalogPage (strength) — catálogo vacío con filtros", () => {
  beforeEach(() => {
    mswServer.use(strengthEmptyCatalogHandler, ...strengthHandlers);
  });

  it("muestra 'Sin resultados para estos filtros' tras aplicar un filtro", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByLabelText("Equipo"), "sin_equipo");

    await waitFor(() => {
      expect(
        screen.getByText("Sin resultados para estos filtros"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText("Ajusta o limpia los filtros para ver más ejercicios."),
    ).toBeInTheDocument();
  });

  it("muestra el copy diferenciado para la combinación conocida equipo_gym × 10-12", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByLabelText("Equipo"), "equipo_gym");
    await user.selectOptions(screen.getByLabelText("Franja de edad"), "10-12");

    await waitFor(() => {
      expect(
        screen.getByText(
          "Aún no hay ejercicios con equipo de gimnasio para 10–12 años",
        ),
      ).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: estado exitoso con datos
// ---------------------------------------------------------------------------

describe("CatalogPage (strength) — estado exitoso", () => {
  beforeEach(() => {
    mswServer.use(...strengthHandlers);
  });

  it("renderiza las tarjetas de ejercicios recibidas de la API", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Sentadilla con peso corporal")).toBeInTheDocument();
    });
    expect(screen.getByText("Press de banca con mancuernas")).toBeInTheDocument();
  });

  it("cada tarjeta enlaza a la ruta de detalle del ejercicio", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Sentadilla con peso corporal")).toBeInTheDocument();
    });
    const link = screen.getByRole("link", { name: "Sentadilla con peso corporal" });
    expect(link).toHaveAttribute("href", "/strength/exercises/1");
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("CatalogPage (strength) — accesibilidad", () => {
  beforeEach(() => {
    mswServer.use(...strengthHandlers);
  });

  it("no tiene violaciones de accesibilidad durante la carga del catálogo", async () => {
    const { container } = renderPage();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con el catálogo cargado", async () => {
    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByText("Sentadilla con peso corporal")).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
