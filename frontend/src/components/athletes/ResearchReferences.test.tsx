import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResearchReferences } from "./ResearchReferences";

// ResearchReferences no depende de Recharts ni de JSON externos — no requiere mocks.

describe("ResearchReferences", () => {
  // 1. Renderiza el botón de toggle colapsable
  it("renderiza el botón de toggle colapsable", () => {
    render(<ResearchReferences />);
    const button = screen.getByRole("button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent(/Fuentes bibliográficas/i);
  });

  // 2. El botón indica cuántas referencias hay (número entre paréntesis)
  it("el botón muestra la cantidad de referencias", () => {
    render(<ResearchReferences />);
    // El texto del botón es "Fuentes bibliográficas (7)"
    expect(screen.getByRole("button")).toHaveTextContent(/\(\d+\)/);
  });

  // 3. Por defecto la lista NO es visible (estado colapsado inicial)
  it("por defecto las referencias están colapsadas", () => {
    render(<ResearchReferences />);
    // Los links no deben existir antes del primer click
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  // 4. Click en el toggle: muestra las referencias
  it("al hacer click en el toggle muestra las referencias", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThanOrEqual(5);
  });

  // 5. Todas las referencias tienen target="_blank"
  it("todas las referencias tienen target='_blank'", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    const links = screen.getAllByRole("link");
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
    }
  });

  // 6. Todas las referencias tienen rel="noreferrer" (seguridad)
  it("todas las referencias tienen rel='noreferrer'", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    const links = screen.getAllByRole("link");
    for (const link of links) {
      expect(link).toHaveAttribute("rel", "noreferrer");
    }
  });

  // 7. Los links apuntan a URLs con href (no vacíos)
  it("todos los links tienen href definido y no vacío", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    const links = screen.getAllByRole("link");
    for (const link of links) {
      const href = link.getAttribute("href");
      expect(href).toBeTruthy();
      expect(href!.length).toBeGreaterThan(0);
    }
  });

  // 8. Al menos 5 links están presentes tras abrir
  it("al expandir hay al menos 5 referencias", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    expect(screen.getAllByRole("link").length).toBeGreaterThanOrEqual(5);
  });

  // 9. Segundo click en toggle: colapsa las referencias
  it("segundo click en el toggle colapsa las referencias", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    const button = screen.getByRole("button");
    await user.click(button);
    // Confirmar que están visibles
    expect(screen.getAllByRole("link").length).toBeGreaterThan(0);
    // Cerrar
    await user.click(button);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  // 10. El botón expone aria-expanded correctamente
  it("aria-expanded es false por defecto y true tras el click", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  // 11. Contiene referencia a la OMS (el título del enlace)
  it("contiene referencia a la OMS", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    // El texto "OMS — Growth Reference Data 5-19 years" aparece en el título y en la desc.
    // Usamos getAllByText para manejar múltiples coincidencias.
    const matches = screen.getAllByText(/OMS/i);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // 12. Contiene referencia a la Resolución 2465
  it("contiene referencia a la Resolución 2465 de MinSalud Colombia", async () => {
    const user = userEvent.setup();
    render(<ResearchReferences />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText(/Resolución 2465/i)).toBeInTheDocument();
  });
});
