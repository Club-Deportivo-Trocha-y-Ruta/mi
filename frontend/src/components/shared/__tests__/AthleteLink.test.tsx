/**
 * Tests para AthleteLink (specs/028-frontend-design-foundation).
 *
 * Cubre el bug que corrige el componente: `/athletes/:id` está restringida a
 * `UserRole.coach` en App.tsx — un <Link> normal hacia esa ruta, visto por
 * admin, sería seguido y ProtectedRoute rebotaría en silencio al dashboard.
 * Casos:
 *  - rol coach: <Link> con href correcto (con y sin `tab`).
 *  - rol admin: <span> sin rol "link" y sin navegación al hacer click.
 *  - `className` idéntico en ambas ramas.
 *  - a11y: jest-axe sin violaciones en ambos casos.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

// `vi.hoisted` corre antes de que los imports se resuelvan — mismo patrón
// que ActivityCard.test.tsx para poder alternar el rol entre tests del mismo
// archivo sin remockear el módulo completo.
const authState = vi.hoisted(() => ({
  role: "coach" as string | undefined,
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { user: { id: number; role: string | undefined } | null }) => unknown,
  ) => selector({ user: { id: 1, role: authState.role } }),
}));

import { AthleteLink } from "../AthleteLink";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Muestra pathname+search actuales para verificar que no hubo navegación. */
function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location-display">{location.pathname + location.search}</div>;
}

type RenderOverrides = Partial<Omit<Parameters<typeof AthleteLink>[0], "children">>;

function renderAthleteLink(props: RenderOverrides = {}) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      {/* Hermano de <Routes>, no hijo de una de sus rutas: sigue montado sin
          importar qué ruta esté activa, así que sirve para verificar
          navegación (o su ausencia) sin depender del contenido de la página. */}
      <LocationDisplay />
      <Routes>
        <Route
          path="/"
          element={
            <AthleteLink athleteId={42} {...props}>
              Sofía Ramírez
            </AthleteLink>
          }
        />
        <Route path="/athletes/:id" element={<div>Detalle del atleta</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AthleteLink", () => {
  beforeEach(() => {
    authState.role = "coach";
  });

  // -------------------------------------------------------------------------
  // rol coach (con acceso a /athletes/:id)
  // -------------------------------------------------------------------------
  describe("cuando el usuario actual es coach", () => {
    it("debería renderizar un <Link> (role='link')", () => {
      renderAthleteLink();
      expect(screen.getByRole("link")).toBeInTheDocument();
    });

    it("debería apuntar a /athletes/{athleteId} cuando no se pasa tab", () => {
      renderAthleteLink();
      expect(screen.getByRole("link")).toHaveAttribute("href", "/athletes/42");
    });

    it("debería añadir el query param ?tab= cuando se pasa tab", () => {
      renderAthleteLink({ tab: "activities" });
      expect(screen.getByRole("link")).toHaveAttribute("href", "/athletes/42?tab=activities");
    });

    it("debería renderizar children dentro del link", () => {
      renderAthleteLink();
      const link = screen.getByRole("link");
      expect(link).toHaveTextContent("Sofía Ramírez");
    });

    it("debería aplicar el className pasado al <Link>", () => {
      renderAthleteLink({ className: "font-display text-charcoal" });
      const link = screen.getByRole("link");
      expect(link.className).toContain("font-display");
      expect(link.className).toContain("text-charcoal");
    });

    it("debería navegar a la ruta del atleta al hacer click", async () => {
      const user = userEvent.setup();
      renderAthleteLink();
      await user.click(screen.getByRole("link"));
      expect(screen.getByTestId("location-display")).toHaveTextContent("/athletes/42");
    });

    it("no debería tener violaciones jest-axe", async () => {
      const { container } = renderAthleteLink();
      expect(await axe(container)).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // rol admin (SIN acceso a /athletes/:id — el bug que corrige el componente)
  // -------------------------------------------------------------------------
  describe("cuando el usuario actual es admin", () => {
    beforeEach(() => {
      authState.role = "admin";
    });

    it("no debería renderizar ningún elemento con role='link'", () => {
      renderAthleteLink();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });

    it("debería renderizar un <span> en su lugar", () => {
      renderAthleteLink();
      const node = screen.getByText("Sofía Ramírez");
      expect(node.tagName).toBe("SPAN");
    });

    it("debería seguir mostrando los children como texto plano", () => {
      renderAthleteLink();
      expect(screen.getByText("Sofía Ramírez")).toBeInTheDocument();
    });

    it("debería aplicar el mismo className al <span> (paridad visual con el link)", () => {
      renderAthleteLink({ className: "font-display text-charcoal" });
      const node = screen.getByText("Sofía Ramírez");
      expect(node.className).toContain("font-display");
      expect(node.className).toContain("text-charcoal");
    });

    it("no debería navegar al hacer click (sin href, sin cambio de ruta)", async () => {
      const user = userEvent.setup();
      renderAthleteLink();
      const node = screen.getByText("Sofía Ramírez");
      expect(node).not.toHaveAttribute("href");
      await user.click(node);
      expect(screen.getByTestId("location-display")).toHaveTextContent("/");
      expect(screen.queryByText("Detalle del atleta")).not.toBeInTheDocument();
    });

    it("no debería tener violaciones jest-axe", async () => {
      const { container } = renderAthleteLink();
      expect(await axe(container)).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Sin sesión / rol no reconocido: por seguridad, nunca debería enlazar.
  // -------------------------------------------------------------------------
  describe("cuando no hay usuario autenticado", () => {
    beforeEach(() => {
      authState.role = undefined;
    });

    it("debería renderizar un <span> (nunca un link) por defecto seguro", () => {
      renderAthleteLink();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.getByText("Sofía Ramírez").tagName).toBe("SPAN");
    });
  });
});
