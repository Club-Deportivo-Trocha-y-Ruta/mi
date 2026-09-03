import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";

import { RegenerateDialog } from "@/components/newsletter/studio/RegenerateDialog";

describe("RegenerateDialog", () => {
  it("confirma sin instrucción envía undefined", () => {
    const onConfirm = vi.fn();
    render(
      <RegenerateDialog
        open
        blockTitle="Título de la etapa"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("regenerate-dialog-confirm"));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("confirma con instrucción la envía recortada", () => {
    const onConfirm = vi.fn();
    render(
      <RegenerateDialog
        open
        blockTitle="Título de la etapa"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Indicación para la regeneración"), {
      target: { value: "  más corto y menciona la lluvia  " },
    });
    fireEvent.click(screen.getByTestId("regenerate-dialog-confirm"));
    expect(onConfirm).toHaveBeenCalledWith("más corto y menciona la lluvia");
  });

  it("trunca la instrucción a 200 caracteres", () => {
    render(
      <RegenerateDialog
        open
        blockTitle="Título"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    const textarea = screen.getByLabelText("Indicación para la regeneración") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "a".repeat(250) } });
    expect(textarea.value).toHaveLength(200);
  });

  it("cancelar llama a onCancel", () => {
    const onCancel = vi.fn();
    render(
      <RegenerateDialog open blockTitle="Título" onConfirm={() => {}} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <RegenerateDialog open blockTitle="Título" onConfirm={() => {}} onCancel={() => {}} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
