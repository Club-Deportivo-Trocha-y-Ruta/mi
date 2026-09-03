import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";

import { BlockCard } from "@/components/newsletter/studio/BlockCard";

describe("BlockCard", () => {
  it("muestra el estado, el título y el contador de palabras", () => {
    render(
      <BlockCard
        dataBlock="stage_title"
        title="Título de la etapa"
        state="ai"
        value="Un mes de frenadas más firmes"
      />,
    );
    expect(screen.getByText("Título de la etapa")).toBeInTheDocument();
    expect(screen.getByText("IA")).toBeInTheDocument();
    expect(screen.getByTestId("block-word-count-stage_title")).toHaveTextContent("6 palabras");
  });

  it("editar y guardar llama a onSave con el texto editado", () => {
    const onSave = vi.fn();
    render(
      <BlockCard
        dataBlock="stage_title"
        title="Título de la etapa"
        state="ai"
        value="Texto original"
        onSave={onSave}
      />,
    );
    fireEvent.click(screen.getByTestId("block-edit-stage_title"));
    const textarea = screen.getByLabelText("Editar Título de la etapa");
    fireEvent.change(textarea, { target: { value: "Texto editado por el coach" } });
    fireEvent.click(screen.getByTestId("block-save-stage_title"));
    expect(onSave).toHaveBeenCalledWith("Texto editado por el coach");
  });

  it("cancelar descarta el draft sin llamar a onSave", () => {
    const onSave = vi.fn();
    render(
      <BlockCard
        dataBlock="stage_title"
        title="Título"
        state="ai"
        value="Original"
        onSave={onSave}
      />,
    );
    fireEvent.click(screen.getByTestId("block-edit-stage_title"));
    fireEvent.change(screen.getByLabelText("Editar Título"), {
      target: { value: "Cambio descartado" },
    });
    fireEvent.click(screen.getByText("Cancelar"));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Original")).toBeInTheDocument();
  });

  it("botón Regenerar llama a onRegenerateClick", () => {
    const onRegenerateClick = vi.fn();
    render(
      <BlockCard
        dataBlock="stage_title"
        title="Título"
        state="ai"
        value="Texto"
        onRegenerateClick={onRegenerateClick}
      />,
    );
    fireEvent.click(screen.getByTestId("block-regenerate-stage_title"));
    expect(onRegenerateClick).toHaveBeenCalledTimes(1);
  });

  it("botón Ocultar/Mostrar alterna según `hidden` y llama a onHideToggle", () => {
    const onHideToggle = vi.fn();
    const { rerender } = render(
      <BlockCard
        dataBlock="photos"
        title="Fotos"
        state="static"
        value=""
        editable={false}
        regenerable={false}
        hideable
        hidden={false}
        onHideToggle={onHideToggle}
      />,
    );
    fireEvent.click(screen.getByTestId("block-hide-toggle-photos"));
    expect(onHideToggle).toHaveBeenCalledTimes(1);

    rerender(
      <BlockCard
        dataBlock="photos"
        title="Fotos"
        state="hidden"
        value=""
        editable={false}
        regenerable={false}
        hideable
        hidden
        onHideToggle={onHideToggle}
      />,
    );
    expect(screen.getByTestId("block-hide-toggle-photos")).toHaveTextContent("Mostrar");
  });

  it("no editable: no muestra botón Editar ni contador de palabras", () => {
    render(
      <BlockCard
        dataBlock="badges"
        title="Insignias"
        state="static"
        value=""
        editable={false}
        regenerable={false}
      />,
    );
    expect(screen.queryByTestId("block-edit-badges")).not.toBeInTheDocument();
    expect(screen.queryByTestId("block-word-count-badges")).not.toBeInTheDocument();
  });

  it("click en el título llama a onCardClick", () => {
    const onCardClick = vi.fn();
    render(
      <BlockCard
        dataBlock="stage_title"
        title="Título"
        state="ai"
        value="Texto"
        onCardClick={onCardClick}
      />,
    );
    fireEvent.click(screen.getByTestId("block-title-stage_title"));
    expect(onCardClick).toHaveBeenCalledTimes(1);
  });

  it("click en el botón Regenerar no dispara onCardClick", () => {
    const onCardClick = vi.fn();
    const onRegenerateClick = vi.fn();
    render(
      <BlockCard
        dataBlock="stage_title"
        title="Título"
        state="ai"
        value="Texto"
        onCardClick={onCardClick}
        onRegenerateClick={onRegenerateClick}
      />,
    );
    fireEvent.click(screen.getByTestId("block-regenerate-stage_title"));
    expect(onCardClick).not.toHaveBeenCalled();
    expect(onRegenerateClick).toHaveBeenCalledTimes(1);
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <BlockCard
        dataBlock="stage_title"
        title="Título de la etapa"
        state="edited"
        value="Texto editado"
        hideable
        onHideToggle={() => {}}
        onRegenerateClick={() => {}}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
