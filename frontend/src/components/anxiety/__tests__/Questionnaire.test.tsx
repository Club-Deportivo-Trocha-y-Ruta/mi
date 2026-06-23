/**
 * Tests para Questionnaire (US2).
 *  - Una pregunta a la vez (avanza con "Siguiente").
 *  - Botones de escala con objetivo táctil ≥48px (min-h-12).
 *  - Sin texto clínico/interpretaciones en el flujo del atleta.
 *  - onSubmit entrega el mapa de respuestas.
 *  - a11y: jest-axe sin violaciones.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { Questionnaire } from "../Questionnaire";
import type { AnswerForm } from "@/types/anxiety.types";

expect.extend(toHaveNoViolations);

const FORM: AnswerForm = {
  instrument_type: "csai2r",
  intro: "Antes de tu carrera, cuéntanos cómo te sientes hoy.",
  scale_min: 1,
  scale_max: 4,
  items: [
    { item_id: 1, text: "Me siento nervioso" },
    { item_id: 2, text: "Mi cuerpo está tenso" },
  ],
};

describe("Questionnaire", () => {
  it("muestra una pregunta a la vez", () => {
    render(<Questionnaire form={FORM} onSubmit={vi.fn()} />);
    expect(screen.getByText("Me siento nervioso")).toBeInTheDocument();
    expect(screen.queryByText("Mi cuerpo está tenso")).not.toBeInTheDocument();
    expect(screen.getByText(/Pregunta 1 de 2/)).toBeInTheDocument();
  });

  it("escala con objetivos táctiles ≥48px (min-h-12)", () => {
    render(<Questionnaire form={FORM} onSubmit={vi.fn()} />);
    const nada = screen.getByRole("button", { name: /Nada/ });
    expect(nada.className).toMatch(/min-h-12/);
  });

  it("avanza y envía el mapa de respuestas", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Questionnaire form={FORM} onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: /Un poco/ }));
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(screen.getByText("Mi cuerpo está tenso")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Mucho/ }));
    await user.click(screen.getByRole("button", { name: "Enviar" }));

    expect(onSubmit).toHaveBeenCalledWith({ 1: 2, 2: 4 });
  });

  it("no muestra texto clínico ni interpretaciones", () => {
    render(<Questionnaire form={FORM} onSubmit={vi.fn()} />);
    expect(screen.queryByText(/diagn/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ansiedad/i)).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <Questionnaire form={FORM} onSubmit={vi.fn()} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
