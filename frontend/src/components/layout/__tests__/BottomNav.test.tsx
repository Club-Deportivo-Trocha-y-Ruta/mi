import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

import { BottomNav } from "@/components/layout/BottomNav";
import type { NavRole } from "@/lib/navigation";

// T031 [US3] — role variants (coach vs. admin 4th slot), aria-current on the
// active slot, >=48x48px target sizing, and the "Más" trigger's
// aria-haspopup/aria-expanded. Per contracts/mobile-navigation.md
// "Bottom bar structure" + data-model.md §3.

function renderBottomNav(
  role: NavRole,
  { initialPath = "/dashboard", open = false }: { initialPath?: string; open?: boolean } = {},
) {
  const onOpenChange = vi.fn();
  const utils = render(
    <MemoryRouter initialEntries={[initialPath]}>
      <BottomNav role={role} open={open} onOpenChange={onOpenChange} />
    </MemoryRouter>,
  );
  return { onOpenChange, ...utils };
}

describe("BottomNav — variantes por rol (contracts/mobile-navigation.md)", () => {
  it("coach ve Inicio, Entrenamiento, Competencias, Atletas y Más (orden fijo)", () => {
    renderBottomNav("coach");

    const nav = screen.getByRole("navigation", { name: "Navegación principal" });
    const labels = ["Inicio", "Entrenamiento", "Competencias", "Atletas"];
    for (const label of labels) {
      expect(
        screen.getByRole("link", { name: new RegExp(label) }),
      ).toBeInTheDocument();
    }
    expect(
      screen.getByRole("button", { name: /Más/ }),
    ).toBeInTheDocument();

    // Order: 4 links then the "Más" button, in the fixed sequence.
    const linkNames = Array.from(nav.querySelectorAll("a")).map((a) =>
      a.textContent?.trim(),
    );
    expect(linkNames).toEqual(labels);
  });

  it("coach NO ve Familias en la barra (4º slot es Atletas)", () => {
    renderBottomNav("coach");

    expect(
      screen.queryByRole("link", { name: /Familias/ }),
    ).not.toBeInTheDocument();
  });

  it("admin ve Inicio, Entrenamiento, Competencias y Más — sin 4º slot (research R6)", () => {
    renderBottomNav("admin");

    const labels = ["Inicio", "Entrenamiento", "Competencias"];
    for (const label of labels) {
      expect(
        screen.getByRole("link", { name: new RegExp(label) }),
      ).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: /Familias/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Más/ })).toBeInTheDocument();
  });

  it("admin NO ve Atletas en la barra (área invisible para admin)", () => {
    renderBottomNav("admin");

    expect(
      screen.queryByRole("link", { name: /Atletas/ }),
    ).not.toBeInTheDocument();
  });
});

describe("BottomNav — aria-current en el slot activo", () => {
  it("el slot cuya área está activa recibe aria-current='page'", () => {
    renderBottomNav("coach", { initialPath: "/calendar" });

    const activeLink = screen.getByRole("link", { name: /Entrenamiento/ });
    expect(activeLink).toHaveAttribute("aria-current", "page");
  });

  it("un deep link dentro de un área (p.ej. /athletes/1 → Atletas) marca ese slot activo", () => {
    renderBottomNav("coach", { initialPath: "/athletes/1" });

    const activeLink = screen.getByRole("link", { name: /Atletas/ });
    expect(activeLink).toHaveAttribute("aria-current", "page");
  });

  it("los slots inactivos no tienen aria-current", () => {
    renderBottomNav("coach", { initialPath: "/calendar" });

    const inicio = screen.getByRole("link", { name: /Inicio/ });
    expect(inicio).not.toHaveAttribute("aria-current");
  });
});

describe("BottomNav — tamaño de objetivo táctil >=48x48px (FR-005)", () => {
  it("cada slot (4 links + botón Más) tiene min-h-[48px] y min-w-[48px]", () => {
    renderBottomNav("coach");

    const slots = [
      screen.getByRole("link", { name: /Inicio/ }),
      screen.getByRole("link", { name: /Entrenamiento/ }),
      screen.getByRole("link", { name: /Competencias/ }),
      screen.getByRole("link", { name: /Atletas/ }),
      screen.getByRole("button", { name: /Más/ }),
    ];

    for (const slot of slots) {
      expect(slot.className).toMatch(/min-h-\[48px\]/);
      expect(slot.className).toMatch(/min-w-\[48px\]/);
    }
  });
});

describe("BottomNav — disparador 'Más' (aria-haspopup/aria-expanded)", () => {
  it("aria-haspopup='dialog' siempre presente", () => {
    renderBottomNav("coach", { open: false });

    expect(screen.getByRole("button", { name: /Más/ })).toHaveAttribute(
      "aria-haspopup",
      "dialog",
    );
  });

  it("aria-expanded refleja la prop `open` (false)", () => {
    renderBottomNav("coach", { open: false });

    expect(screen.getByRole("button", { name: /Más/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("aria-expanded refleja la prop `open` (true)", () => {
    renderBottomNav("coach", { open: true });

    expect(screen.getByRole("button", { name: /Más/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("hacer click invoca onOpenChange con el valor invertido", async () => {
    const { onOpenChange } = renderBottomNav("coach", { open: false });
    const trigger = screen.getByRole("button", { name: /Más/ });

    trigger.click();

    expect(onOpenChange).toHaveBeenCalledWith(true);
  });
});

describe("BottomNav — accesibilidad (jest-axe)", () => {
  it("sin violaciones axe (coach)", async () => {
    const { container } = renderBottomNav("coach");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe (admin)", async () => {
    const { container } = renderBottomNav("admin");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
