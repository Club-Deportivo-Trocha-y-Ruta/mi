import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { QuickCreate } from "@/components/layout/QuickCreate";
import type { NavRole } from "@/lib/navigation";

// T040 [US4] — role-filtered items (Nuevo atleta coach-only), each item
// links to its documented route with no ?prefill params, y el trigger cumple
// el objetivo táctil. Per contracts/header-actions.md.
//
// Feature 035 (Main.dc.html): el trigger pasó de botón de sólo ícono a botón
// primario etiquetado (Plus + «Crear» + chevron, 44px de alto = el `min-h-11`
// de la variante por defecto de ui/button.tsx). Se conservan intactos el
// `aria-label="Crear"`, el `data-testid` y la lista de items.

function renderQuickCreate(role: NavRole) {
  return render(
    <MemoryRouter>
      <QuickCreate role={role} />
    </MemoryRouter>,
  );
}

describe("QuickCreate — trigger", () => {
  it("renderiza un botón con aria-label 'Crear'", () => {
    renderQuickCreate("coach");
    expect(screen.getByLabelText("Crear")).toBeInTheDocument();
  });

  it("muestra la etiqueta visible «Crear» y conserva su data-testid", () => {
    renderQuickCreate("coach");

    const trigger = screen.getByTestId("quick-create-trigger");
    expect(trigger).toHaveTextContent("Crear");
    // aria-label idéntico al texto visible (WCAG 2.5.3 Label in Name).
    expect(trigger).toHaveAttribute("aria-label", "Crear");
    expect(screen.getByLabelText("Crear")).toBe(trigger);
  });

  it("el trigger es un botón primario que cumple el objetivo táctil (>=48px)", () => {
    renderQuickCreate("coach");
    const trigger = screen.getByTestId("quick-create-trigger");
    // min-h-12 (48px): el tamaño `default` de buttonVariants() sólo asegura
    // 44px y el piso del proyecto es 48 — el e2e mide esta altura real.
    expect(trigger.className).toMatch(/min-h-12/);
    expect(trigger.className).toMatch(/bg-primary/);
  });

  it("la etiqueta va en tinta oscura sobre el relleno turquesa (contraste AA)", () => {
    renderQuickCreate("coach");
    const trigger = screen.getByTestId("quick-create-trigger");
    // Blanco sobre --color-primary (#20b7c9) da 2.42:1 y falla AA para 14px;
    // #111111 da 7.8:1 y no se invierte con el tema (a diferencia de
    // --color-charcoal), igual que --color-primary.
    expect(trigger.className).toMatch(/text-midnight/);
    expect(trigger.className).not.toMatch(/text-white/);
  });

  it("acompaña la etiqueta con los íconos Plus y chevron (decorativos)", () => {
    renderQuickCreate("coach");

    const icons = screen
      .getByTestId("quick-create-trigger")
      .querySelectorAll("svg");
    expect(icons).toHaveLength(2);
    for (const icon of icons) {
      expect(icon).toHaveAttribute("aria-hidden", "true");
    }
  });
});

describe("QuickCreate — filtrado por rol", () => {
  it("coach ve las 4 opciones, incluyendo 'Nuevo atleta'", async () => {
    const user = userEvent.setup();
    renderQuickCreate("coach");

    await user.click(screen.getByTestId("quick-create-trigger"));

    expect(screen.getByTestId("quick-create.session")).toBeInTheDocument();
    expect(screen.getByTestId("quick-create.competition")).toBeInTheDocument();
    expect(screen.getByTestId("quick-create.event")).toBeInTheDocument();
    expect(screen.getByTestId("quick-create.athlete")).toBeInTheDocument();
  });

  it("admin NO ve 'Nuevo atleta' (coach-only)", async () => {
    const user = userEvent.setup();
    renderQuickCreate("admin");

    await user.click(screen.getByTestId("quick-create-trigger"));

    expect(screen.getByTestId("quick-create.session")).toBeInTheDocument();
    expect(screen.getByTestId("quick-create.competition")).toBeInTheDocument();
    expect(screen.getByTestId("quick-create.event")).toBeInTheDocument();
    expect(
      screen.queryByTestId("quick-create.athlete"),
    ).not.toBeInTheDocument();
  });
});

describe("QuickCreate — destinos sin parámetros ?prefill", () => {
  it("coach: cada item enlaza a su ruta documentada, sin query params", async () => {
    const user = userEvent.setup();
    renderQuickCreate("coach");

    await user.click(screen.getByTestId("quick-create-trigger"));

    const expected: Record<string, string> = {
      "quick-create.session": "/training/sessions/new",
      "quick-create.competition": "/competitions/new",
      "quick-create.event": "/calendar/events/new",
      "quick-create.athlete": "/athletes/new",
    };

    for (const [testId, href] of Object.entries(expected)) {
      const item = screen.getByTestId(testId);
      const link = item.tagName === "A" ? item : item.querySelector("a");
      expect(link).toHaveAttribute("href", href);
      expect(link?.getAttribute("href")).not.toMatch(/\?/);
    }
  });

  it("admin: los items visibles enlazan a su ruta documentada, sin query params", async () => {
    const user = userEvent.setup();
    renderQuickCreate("admin");

    await user.click(screen.getByTestId("quick-create-trigger"));

    const expected: Record<string, string> = {
      "quick-create.session": "/training/sessions/new",
      "quick-create.competition": "/competitions/new",
      "quick-create.event": "/calendar/events/new",
    };

    for (const [testId, href] of Object.entries(expected)) {
      const item = screen.getByTestId(testId);
      const link = item.tagName === "A" ? item : item.querySelector("a");
      expect(link).toHaveAttribute("href", href);
      expect(link?.getAttribute("href")).not.toMatch(/\?/);
    }
  });
});
