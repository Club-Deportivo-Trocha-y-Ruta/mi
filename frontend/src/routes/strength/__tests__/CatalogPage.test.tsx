/**
 * Tests para CatalogPage (feature 030 / T022, US2) — "Armar bloque":
 *   - El botón/enlace "Armar bloque" se renderiza en el encabezado.
 *   - Apunta a `/strength/blocks/new` (el armador de bloques de fuerza,
 *     antes solo alcanzable desde el detalle de una sesión de entrenamiento).
 *   - Sin violaciones de accesibilidad con el catálogo cargado.
 *
 * Este archivo no existía previamente para esta página (feature 021 no dejó
 * un CatalogPage.test.tsx bajo strength/__tests__/). Sigue el patrón de
 * `components/technique/__tests__/CatalogPage.test.tsx` (MSW real vía
 * mswServer.use(...strengthHandlers), sin mock de useAuthStore ya que
 * CatalogPage no lee el rol del usuario).
 */
import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { CatalogPage } from "@/routes/strength/CatalogPage";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import { strengthHandlers } from "@/test/msw/strengthHandlers";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return renderWithProviders(<CatalogPage />);
}

beforeEach(() => {
  mswServer.use(...strengthHandlers);
});

// ---------------------------------------------------------------------------
// Suite: encabezado — botón "Armar bloque"
// ---------------------------------------------------------------------------

describe("CatalogPage — botón 'Armar bloque'", () => {
  it("renderiza el enlace 'Armar bloque' en el encabezado", async () => {
    renderPage();
    expect(
      screen.getByRole("link", { name: /Armar bloque/ }),
    ).toBeInTheDocument();
  });

  it("el enlace 'Armar bloque' apunta a /strength/blocks/new", async () => {
    renderPage();
    const link = screen.getByRole("link", { name: /Armar bloque/ });
    expect(link).toHaveAttribute("href", "/strength/blocks/new");
  });
});

// ---------------------------------------------------------------------------
// Suite: encabezado y estructura de página
// ---------------------------------------------------------------------------

describe("CatalogPage — encabezado", () => {
  it("renderiza el título de la página", () => {
    renderPage();
    expect(
      screen.getByRole("heading", {
        name: /Biblioteca de fuerza y acondicionamiento/,
      }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("CatalogPage — accesibilidad", () => {
  it("no tiene violaciones de accesibilidad con el catálogo cargado", async () => {
    const { container } = renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("Sentadilla con peso corporal"),
      ).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
