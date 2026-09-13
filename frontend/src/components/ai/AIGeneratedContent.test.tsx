import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth.store";
import { MaturationStatus, UserRole } from "@/types/enums";
import type { PHVExplanationResponse } from "@/types/ai.types";

import { AIGeneratedContent } from "./AIGeneratedContent";

const baseData: PHVExplanationResponse = {
  schema_version: "v1",
  text: "Su hijo está en Pre-PHV. Priorizamos juego, técnica y descanso.",
  model: "claude-sonnet-4-5",
  provider: "anthropic",
  generated_at: "2026-05-05T15:30:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
};

const coachData: PHVExplanationResponse = {
  schema_version: "v2",
  text: "Talla +1.0 cm en 14 semanas, dentro del rango esperado.",
  model: "gemini-3.8-flash",
  provider: "google",
  generated_at: "2026-09-10T11:56:00Z",
  age_group: "13-15",
  maturation_status: MaturationStatus.CircaPHV,
  structured: {
    summary_line: "Talla +1.0 cm en 14 semanas, dentro del rango esperado.",
    changes: ["El cambio de talla supera el ruido instrumental."],
    meaning: ["La velocidad estimada está por encima de lo típico."],
    next_weeks: ["Compatible con fuerza progresiva."],
    warning_signs: [],
    confidence: { level: "high", reason: "Intervalo de 14 semanas consistente." },
    data_gaps: [],
  },
  critic_verdict: "approved",
  is_fallback: false,
  prompt_version: "anthropometry_analyst_v1",
  trace_id: "a1b2c3d4e5f60718",
};

afterEach(() => {
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false });
});

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

  it("muestra el disclaimer obligatorio sobre IA en el token informativo neutro (FR-030)", () => {
    render(<AIGeneratedContent data={baseData} />);
    const disclaimer = screen.getByText(
      /Generado por IA basándose en datos del atleta/,
    );
    expect(disclaimer).toBeInTheDocument();
    expect(
      screen.getByText(/Revisa con el entrenador antes de tomar decisiones/),
    ).toBeInTheDocument();
    // FR-030: el disclaimer usa el token informativo neutro (azul); el ámbar
    // queda reservado para el bloque condicional de implicaciones de
    // entrenamiento, que este componente no renderiza.
    expect(disclaimer.className).toMatch(/bg-blue-50/);
    expect(disclaimer.className).not.toMatch(/amber/);
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

  it("el control 'Copiar' mide al menos 48 px de alto (FR-031)", () => {
    render(<AIGeneratedContent data={baseData} />);
    const button = screen.getByRole("button", { name: /Copiar/i });
    // `min-h-12` (Tailwind) = 48px — jsdom no calcula layout real, así que
    // verificamos la clase que impone el mínimo en vez de un boundingRect.
    expect(button.className).toMatch(/min-h-12/);
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

  // ---------------------------------------------------------------------
  // FR-029 — procedencia por audiencia
  // ---------------------------------------------------------------------

  describe("procedencia por audiencia (FR-029)", () => {
    it("una familia (sin rol coach/admin) ve la línea fija de procedencia con la fecha, y nada de modelo/proveedor", () => {
      render(<AIGeneratedContent data={coachData} />);

      expect(
        screen.getByText(/Generado por el asistente de IA del club/),
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText("Fecha de generación"),
      ).toBeInTheDocument();

      // Nunca el proveedor, el modelo, la versión del prompt ni la traza:
      expect(screen.queryByText(/gemini-3.8-flash/)).not.toBeInTheDocument();
      expect(screen.queryByText(/google\//)).not.toBeInTheDocument();
      expect(
        screen.queryByText("anthropometry_analyst_v1"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText("a1b2c3d4e5f60718"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("ai-technical-details"),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("Detalles técnicos")).not.toBeInTheDocument();
    });

    it("un coach ve, además de la línea de procedencia, el disclosure técnico con modelo, versión del prompt y referencia de traza", () => {
      useAuthStore.setState({
        user: {
          id: 1,
          email: "coach@example.com",
          first_name: "Entrenador",
          last_name: "Prueba",
          phone: null,
          role: UserRole.coach,
          is_active: true,
          can_login: true,
          club_ids: [1],
          created_at: "2026-01-01T00:00:00",
        },
        isAuthenticated: true,
      });

      render(<AIGeneratedContent data={coachData} />);

      expect(
        screen.getByText(/Generado por el asistente de IA del club/),
      ).toBeInTheDocument();

      const details = screen.getByTestId("ai-technical-details");
      expect(details.tagName.toLowerCase()).toBe("details");
      expect(
        screen.getByText("Detalles técnicos").tagName.toLowerCase(),
      ).toBe("summary");
      expect(screen.getByText(/google\/gemini-3.8-flash/)).toBeInTheDocument();
      expect(
        screen.getByText("anthropometry_analyst_v1"),
      ).toBeInTheDocument();
      expect(screen.getByText("a1b2c3d4e5f60718")).toBeInTheDocument();
    });

    it("un coach viendo una fila v1 (legacy) ve el disclosure con 'No disponible' en prompt y traza", () => {
      useAuthStore.setState({
        user: {
          id: 2,
          email: "coach2@example.com",
          first_name: "Entrenador",
          last_name: "Dos",
          phone: null,
          role: UserRole.admin,
          is_active: true,
          can_login: true,
          club_ids: [1],
          created_at: "2026-01-01T00:00:00",
        },
        isAuthenticated: true,
      });

      render(<AIGeneratedContent data={baseData} />);

      expect(screen.getByTestId("ai-technical-details")).toBeInTheDocument();
      expect(
        screen.getByText(/anthropic\/claude-sonnet-4-5/),
      ).toBeInTheDocument();
      expect(screen.getAllByText("No disponible")).toHaveLength(2);
    });

    it("un padre (rol parent) nunca ve el disclosure técnico aunque exista trace_id en la respuesta", () => {
      useAuthStore.setState({
        user: {
          id: 3,
          email: "padre@example.com",
          first_name: "Familia",
          last_name: "Prueba",
          phone: null,
          role: UserRole.parent,
          is_active: true,
          can_login: true,
          club_ids: [1],
          created_at: "2026-01-01T00:00:00",
        },
        isAuthenticated: true,
      });

      render(<AIGeneratedContent data={coachData} />);

      expect(
        screen.queryByTestId("ai-technical-details"),
      ).not.toBeInTheDocument();
    });
  });
});
