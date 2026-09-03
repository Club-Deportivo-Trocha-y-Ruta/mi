import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";

import { BlockPanel } from "@/components/newsletter/studio/BlockPanel";
import { buildStageLogFullMonth } from "@/test/fixtures/stageLog";

function setup(overrideProps: Partial<React.ComponentProps<typeof BlockPanel>> = {}) {
  const onSaveBlock = vi.fn();
  const onSaveCoachNote = vi.fn();
  const onRegenerateClick = vi.fn();
  const onHideToggle = vi.fn();
  const onScrollToBlock = vi.fn();

  render(
    <BlockPanel
      stageLog={buildStageLogFullMonth()}
      hiddenBlocks={[]}
      onSaveBlock={onSaveBlock}
      onSaveCoachNote={onSaveCoachNote}
      onRegenerateClick={onRegenerateClick}
      onHideToggle={onHideToggle}
      onScrollToBlock={onScrollToBlock}
      {...overrideProps}
    />,
  );

  return { onSaveBlock, onSaveCoachNote, onRegenerateClick, onHideToggle, onScrollToBlock };
}

describe("BlockPanel", () => {
  it("renderiza las 9 tarjetas de bloque", () => {
    setup();
    expect(screen.getByTestId("block-card-header")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-summit")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-observations")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-analyst-reading")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-next-segment")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-family-compass")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-coach-note")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-photos")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-badges")).toBeInTheDocument();
  });

  it("editar el título llama a onSaveBlock con el override correcto", () => {
    const { onSaveBlock } = setup();
    fireEvent.click(screen.getByTestId("block-edit-header"));
    fireEvent.change(screen.getByLabelText("Editar Título de la etapa"), {
      target: { value: "Título editado por el coach" },
    });
    fireEvent.click(screen.getByTestId("block-save-header"));
    expect(onSaveBlock).toHaveBeenCalledWith("stage_title", {
      stage_title: "Título editado por el coach",
    });
  });

  it("editar observaciones reconstruye el arreglo con block_ref preservado", () => {
    const stageLog = buildStageLogFullMonth();
    const { onSaveBlock } = setup({ stageLog });
    fireEvent.click(screen.getByTestId("block-edit-observations"));
    const textarea = screen.getByLabelText("Editar Lo que vio el entrenador");
    fireEvent.change(textarea, {
      target: {
        value: "Asistencia perfecta\n10 de 10 sesiones\n\nTécnica sólida\n4.5/5\n\nBuena carrera\nP1",
      },
    });
    fireEvent.click(screen.getByTestId("block-save-observations"));
    expect(onSaveBlock).toHaveBeenCalledWith("observations", {
      observations: [
        { claim: "Asistencia perfecta", evidence: "10 de 10 sesiones", block_ref: "attendance" },
        { claim: "Técnica sólida", evidence: "4.5/5", block_ref: "technical" },
        { claim: "Buena carrera", evidence: "P1", block_ref: "race" },
      ],
    });
  });

  it("regenerar un bloque llama a onRegenerateClick con el nombre del bloque", () => {
    const { onRegenerateClick } = setup();
    fireEvent.click(screen.getByTestId("block-regenerate-analyst-reading"));
    expect(onRegenerateClick).toHaveBeenCalledWith("analyst_reading");
  });

  it("ocultar un bloque opcional llama a onHideToggle con el nombre correcto", () => {
    const { onHideToggle } = setup();
    fireEvent.click(screen.getByTestId("block-hide-toggle-analyst-reading"));
    expect(onHideToggle).toHaveBeenCalledWith("analyst_reading");
    fireEvent.click(screen.getByTestId("block-hide-toggle-photos"));
    expect(onHideToggle).toHaveBeenCalledWith("photos");
    fireEvent.click(screen.getByTestId("block-hide-toggle-badges"));
    expect(onHideToggle).toHaveBeenCalledWith("badges");
    fireEvent.click(screen.getByTestId("block-hide-toggle-coach-note"));
    expect(onHideToggle).toHaveBeenCalledWith("coach_note");
  });

  it("refleja hiddenBlocks mostrando 'Mostrar' en los bloques ocultos", () => {
    setup({ hiddenBlocks: ["photos", "badges"] });
    expect(screen.getByTestId("block-hide-toggle-photos")).toHaveTextContent("Mostrar");
    expect(screen.getByTestId("block-hide-toggle-badges")).toHaveTextContent("Mostrar");
    expect(screen.getByTestId("block-hide-toggle-analyst-reading")).toHaveTextContent("Ocultar");
  });

  it("click en el título de una tarjeta llama a onScrollToBlock con el anchor del preview", () => {
    const { onScrollToBlock } = setup();
    fireEvent.click(screen.getByTestId("block-title-header"));
    expect(onScrollToBlock).toHaveBeenCalledWith("header");
  });

  it("editar la nota del entrenador llama a onSaveCoachNote (no regenerable)", () => {
    const { onSaveCoachNote } = setup();
    expect(screen.queryByTestId("block-regenerate-coach-note")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("block-edit-coach-note"));
    fireEvent.change(screen.getByLabelText("Editar Nota del entrenador"), {
      target: { value: "Nota nueva del entrenador" },
    });
    fireEvent.click(screen.getByTestId("block-save-coach-note"));
    expect(onSaveCoachNote).toHaveBeenCalledWith("Nota nueva del entrenador");
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <BlockPanel
        stageLog={buildStageLogFullMonth()}
        hiddenBlocks={[]}
        onSaveBlock={() => {}}
        onSaveCoachNote={() => {}}
        onRegenerateClick={() => {}}
        onHideToggle={() => {}}
        onScrollToBlock={() => {}}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
