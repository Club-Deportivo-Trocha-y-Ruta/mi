import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExplainModeBanner } from "@/components/ai/ExplainModeBanner";
import { useExplainModeStore } from "@/store/explainMode.store";

describe("ExplainModeBanner", () => {
  beforeEach(() => {
    // Reset store entre tests para aislamiento.
    useExplainModeStore.setState({ enabled: false });
    try {
      localStorage.clear();
    } catch {
      /* jsdom puede fallar */
    }
  });

  it("renderiza estado desactivado por default", () => {
    render(<ExplainModeBanner />);
    expect(screen.getByText(/Modo aprendizaje desactivado/i)).toBeInTheDocument();
    const toggle = screen.getByTestId("explain-mode-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(toggle).toHaveTextContent(/Activar/);
  });

  it("toggle alterna estado y persiste", async () => {
    const user = userEvent.setup();
    render(<ExplainModeBanner />);
    const toggle = screen.getByTestId("explain-mode-toggle");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Modo aprendizaje activo/i)).toBeInTheDocument();
    expect(useExplainModeStore.getState().enabled).toBe(true);
  });

  it("refleja estado externo del store", () => {
    useExplainModeStore.setState({ enabled: true });
    render(<ExplainModeBanner />);
    expect(screen.getByText(/activo/i)).toBeInTheDocument();
    expect(
      screen.getByText(/narra qué hace en cada nodo/i),
    ).toBeInTheDocument();
  });
});
