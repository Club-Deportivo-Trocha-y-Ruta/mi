/**
 * Tests para NewsletterNarrativeEditor.
 *
 * Cubre: render, edición, validación 500 chars, save override.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { NewsletterNarrativeEditor } from "./NewsletterNarrativeEditor";
import type { AiNarrative, NarrativeOverride } from "@/types/athleteNewsletter.types";

function renderEditor(
  props: Partial<React.ComponentProps<typeof NewsletterNarrativeEditor>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaults = {
    aiNarrative: null,
    currentOverrides: null,
    disabled: false,
    isPending: false,
    onSave: vi.fn(),
    ...props,
  };
  return render(
    <QueryClientProvider client={qc}>
      <NewsletterNarrativeEditor {...defaults} />
    </QueryClientProvider>,
  );
}

const mockAiNarrative: AiNarrative = {
  strengths: "Demostró constancia en el entrenamiento.",
  area_to_develop: "Trabajar la cadencia en subidas.",
  milestone: "Completó el circuito técnico sin parar.",
  model: "gemini-2.5-flash-lite",
  prompt_version: "v1",
  confidence: "medium",
};

const lowConfidenceNarrative: AiNarrative = {
  ...mockAiNarrative,
  confidence: "low",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("NewsletterNarrativeEditor — render", () => {
  it("muestra mensaje cuando no hay narrativa IA", () => {
    renderEditor({ aiNarrative: null });
    expect(screen.getByText(/Sin narrativa generada aún/i)).toBeInTheDocument();
  });

  it("renderiza los 3 campos con la narrativa IA como placeholder/valor", () => {
    renderEditor({ aiNarrative: mockAiNarrative });
    expect(screen.getByLabelText(/Fortalezas/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Area a desarrollar/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Hito del mes/i)).toBeInTheDocument();
  });

  it("muestra badge de confianza media", () => {
    renderEditor({ aiNarrative: mockAiNarrative });
    expect(screen.getByText(/Confianza Media/i)).toBeInTheDocument();
  });

  it("muestra badge de confianza alta", () => {
    renderEditor({ aiNarrative: { ...mockAiNarrative, confidence: "high" } });
    expect(screen.getByText(/Confianza Alta/i)).toBeInTheDocument();
  });

  it("muestra alerta de confianza baja cuando confidence=low", () => {
    renderEditor({ aiNarrative: lowConfidenceNarrative });
    const alert = screen.getByTestId("low-confidence-alert");
    expect(alert).toBeInTheDocument();
    // El texto "Confianza baja" aparece tanto en el badge como en el alert;
    // verificamos específicamente el del alert.
    expect(alert).toHaveTextContent(/Confianza baja/i);
  });

  it("muestra la narrativa IA original como referencia en modo edición", () => {
    renderEditor({ aiNarrative: mockAiNarrative });
    // Hay 3 referencias IA (una por campo); verificamos que existan todas
    expect(screen.getAllByText(/IA:/i)).toHaveLength(3);
  });

  it("muestra botón 'Guardar cambios' cuando no está disabled", () => {
    renderEditor({ aiNarrative: mockAiNarrative });
    expect(screen.getByTestId("save-narrative-btn")).toBeInTheDocument();
  });

  it("no muestra botón guardar cuando disabled=true", () => {
    renderEditor({ aiNarrative: mockAiNarrative, disabled: true });
    expect(screen.queryByTestId("save-narrative-btn")).not.toBeInTheDocument();
  });

  it("muestra vista de solo lectura cuando disabled=true", () => {
    renderEditor({
      aiNarrative: mockAiNarrative,
      disabled: true,
    });
    expect(screen.getByTestId("narrative-readonly")).toBeInTheDocument();
  });

  it("muestra override del coach cuando existe y está disabled", () => {
    const overrides: NarrativeOverride = {
      strengths: "Override del entrenador",
    };
    renderEditor({
      aiNarrative: mockAiNarrative,
      currentOverrides: overrides,
      disabled: true,
    });
    expect(screen.getByText("Override del entrenador")).toBeInTheDocument();
  });
});

describe("NewsletterNarrativeEditor — edición", () => {
  it("puede escribir en el campo fortalezas", async () => {
    const user = userEvent.setup();
    renderEditor({ aiNarrative: mockAiNarrative });
    const field = screen.getByLabelText(/Fortalezas/i) as HTMLTextAreaElement;
    await user.clear(field);
    await user.type(field, "Nueva fortaleza");
    expect(field.value).toBe("Nueva fortaleza");
  });

  it("muestra contador de caracteres", async () => {
    const user = userEvent.setup();
    renderEditor({ aiNarrative: mockAiNarrative });
    const field = screen.getByLabelText(/Fortalezas/i);
    await user.clear(field);
    await user.type(field, "Hola");
    // Debería mostrar 4/500
    const counters = screen.getAllByText(/\/500/);
    expect(counters.length).toBeGreaterThan(0);
  });

  it("llama onSave con los overrides al hacer submit", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    renderEditor({ aiNarrative: mockAiNarrative, onSave });

    const field = screen.getByLabelText(/Fortalezas/i);
    await user.clear(field);
    await user.type(field, "Texto nuevo para fortalezas");

    const form = screen.getByTestId("narrative-editor-form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          strengths: "Texto nuevo para fortalezas",
        }),
      );
    });
  });

  it("muestra badge 'Editado' cuando el campo fue modificado", async () => {
    const user = userEvent.setup();
    renderEditor({ aiNarrative: mockAiNarrative });
    const field = screen.getByLabelText(/Fortalezas/i);
    await user.clear(field);
    await user.type(field, "Diferente texto");
    expect(screen.getByText("Editado")).toBeInTheDocument();
  });
});

describe("NewsletterNarrativeEditor — validación", () => {
  it("el campo tiene maxLength controlado", () => {
    renderEditor({ aiNarrative: mockAiNarrative });
    const fields = screen.getAllByRole("textbox");
    // Cada textarea debe tener maxLength configurado
    fields.forEach((field) => {
      expect(Number((field as HTMLTextAreaElement).maxLength)).toBeGreaterThan(0);
    });
  });

  it("muestra error si un campo supera 500 chars al intentar guardar", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    renderEditor({ aiNarrative: mockAiNarrative, onSave });

    const field = screen.getByLabelText(/Fortalezas/i) as HTMLTextAreaElement;
    // El maxLength en el textarea evita que se escriban más de 510 chars.
    // Para testear la validación Zod sin el maxLength nativo, manipulamos el value directamente.
    const longText = "A".repeat(501);
    await user.clear(field);
    // Usamos fireEvent para evitar la restricción del maxLength del DOM
    fireEvent.change(field, { target: { value: longText } });
    expect(field.value.length).toBe(501);

    const form = screen.getByTestId("narrative-editor-form");
    fireEvent.submit(form);

    await waitFor(() => {
      // Zod valida y debe mostrar error; si pasa, onSave NO debe ser llamado
      expect(onSave).not.toHaveBeenCalled();
    });
  });

  it("los textareas tienen aria-label accesibles", () => {
    renderEditor({ aiNarrative: mockAiNarrative });
    expect(screen.getByRole("textbox", { name: /Fortalezas/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Area a desarrollar/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Hito del mes/i })).toBeInTheDocument();
  });
});

describe("NewsletterNarrativeEditor — estado pending", () => {
  it("muestra spinner en botón guardar cuando isPending=true", () => {
    renderEditor({ aiNarrative: mockAiNarrative, isPending: true });
    const btn = screen.getByTestId("save-narrative-btn");
    expect(btn).toBeDisabled();
    // Spinner svg debe estar presente
    const spinner = btn.querySelector("svg");
    expect(spinner).not.toBeNull();
  });
});
