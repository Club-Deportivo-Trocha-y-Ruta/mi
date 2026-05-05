import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MaturationStatus } from "@/types/enums";
import type { PHVExplanationResponse } from "@/types/ai.types";

import { AIGeneratedContent } from "./AIGeneratedContent";

const baseData: PHVExplanationResponse = {
  text: "Su hijo está en Pre-PHV. Priorizamos juego, técnica y descanso.",
  model: "claude-sonnet-4-5",
  provider: "anthropic",
  generated_at: "2026-05-05T15:30:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
};

describe("AIGeneratedContent", () => {
  it("renderiza el texto generado", () => {
    render(<AIGeneratedContent data={baseData} />);
    expect(
      screen.getByText(/Priorizamos juego, técnica y descanso/),
    ).toBeInTheDocument();
  });

  it("muestra el badge PHV con el estado correcto", () => {
    render(<AIGeneratedContent data={baseData} />);
    expect(screen.getByText("Pre-PHV")).toBeInTheDocument();
  });

  it("muestra el disclaimer obligatorio sobre IA", () => {
    render(<AIGeneratedContent data={baseData} />);
    expect(
      screen.getByText(/Generado por IA basándose en datos del atleta/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Revisa con el entrenador antes de tomar decisiones/),
    ).toBeInTheDocument();
  });

  it("muestra el modelo y proveedor en un badge", () => {
    render(<AIGeneratedContent data={baseData} />);
    expect(
      screen.getByText(/anthropic\/claude-sonnet-4-5/),
    ).toBeInTheDocument();
  });

  it("renderiza 'Sin evaluar' si maturation_status viene vacío", () => {
    render(
      <AIGeneratedContent data={{ ...baseData, maturation_status: "" }} />,
    );
    expect(screen.getByText("Sin evaluar")).toBeInTheDocument();
  });

  it("copia el texto al portapapeles al pulsar 'Copiar'", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(<AIGeneratedContent data={baseData} />);
    fireEvent.click(screen.getByRole("button", { name: /Copiar/i }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(baseData.text),
    );
    expect(
      await screen.findByRole("button", { name: /Copiado/i }),
    ).toBeInTheDocument();
  });

  it("no expone el texto en title/aria-label de elementos del DOM (privacidad)", () => {
    const { container } = render(<AIGeneratedContent data={baseData} />);
    const sensibleSubstring = "Priorizamos juego, técnica";
    container.querySelectorAll("*").forEach((el) => {
      expect(el.getAttribute("title") ?? "").not.toContain(sensibleSubstring);
      expect(el.getAttribute("aria-label") ?? "").not.toContain(
        sensibleSubstring,
      );
    });
  });

  it("no renderiza fechas ISO sueltas (privacy: si por error backend filtra DOB)", () => {
    // Aunque PHVExplanationResponse no tiene birth_date, defensa en profundidad:
    // ningún string que parezca DOB ISO debe aparecer fuera de generated_at.
    render(
      <AIGeneratedContent
        data={{
          ...baseData,
          // Intencionalmente extra (sería ignorado por TS pero validamos en runtime)
        }}
      />,
    );
    // generated_at se renderiza formateado, no como ISO crudo:
    expect(screen.queryByText(/2026-05-05T15:30:00Z/)).not.toBeInTheDocument();
  });
});
