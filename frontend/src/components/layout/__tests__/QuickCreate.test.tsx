import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { QuickCreate } from "@/components/layout/QuickCreate";
import type { NavRole } from "@/lib/navigation";

// T040 [US4] — role-filtered items (Nuevo atleta coach-only), each item
// links to its documented route with no ?prefill params, and the trigger
// meets the >=48x48px touch target. Per contracts/header-actions.md.

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

  it("el trigger cumple el tamaño de objetivo táctil >=48x48px", () => {
    renderQuickCreate("coach");
    const trigger = screen.getByTestId("quick-create-trigger");
    expect(trigger.className).toMatch(/h-12/);
    expect(trigger.className).toMatch(/w-12/);
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
