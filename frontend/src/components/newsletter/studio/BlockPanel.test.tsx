import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { BlockPanel } from "@/components/newsletter/studio/BlockPanel";
import { CHANGE_NOTICE_TEXT } from "@/components/newsletter/studio/changeNotice";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { MeResponse } from "@/types/auth.types";
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


// ---------------------------------------------------------------------------
// Feature 045 (T063) — «Insertar aviso de cambios»
// ---------------------------------------------------------------------------

function makeCoach(id: number): MeResponse {
  return {
    id,
    email: "coach.prueba@example.com",
    first_name: "Entrenador",
    last_name: "Ficticio",
    phone: null,
    role: UserRole.coach,
    is_active: true,
    can_login: true,
    club_ids: [1],
    created_at: "2026-01-01T00:00:00",
  };
}

describe("BlockPanel — aviso de cambios (feature 045, T063)", () => {
  const emptyNote = () => buildStageLogFullMonth({ coach_note: null });

  beforeEach(() => {
    window.localStorage.clear();
    useAuthStore.setState({ user: makeCoach(7), isAuthenticated: true });
  });

  afterEach(() => {
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false });
    window.localStorage.clear();
  });

  it("con la nota vacía ofrece «Insertar aviso de cambios» y «No mostrar más»", () => {
    setup({ stageLog: emptyNote() });
    const offer = screen.getByTestId("change-notice-offer");
    expect(within(offer).getByRole("button", { name: "Insertar aviso de cambios" })).toBeInTheDocument();
    expect(within(offer).getByRole("button", { name: "No mostrar más" })).toBeInTheDocument();
  });

  it("ambos botones cumplen el touch target de 48px", () => {
    setup({ stageLog: emptyNote() });
    expect(screen.getByTestId("change-notice-insert").className).toMatch(/min-h-12/);
    expect(screen.getByTestId("change-notice-dismiss").className).toMatch(/min-h-12/);
  });

  it("un clic abre el editor de la nota con el aviso ya escrito, editable y sin guardar ni enviar nada", () => {
    const { onSaveCoachNote, onSaveBlock } = setup({ stageLog: emptyNote() });
    fireEvent.click(screen.getByTestId("change-notice-insert"));

    const textarea = screen.getByLabelText("Editar Nota del entrenador");
    expect(textarea).toHaveValue(CHANGE_NOTICE_TEXT);
    expect(textarea).toHaveFocus();
    // Aún nada persistido: el coach debe revisar y guardar.
    expect(onSaveCoachNote).not.toHaveBeenCalled();
    expect(onSaveBlock).not.toHaveBeenCalled();
    // El texto cabe en el límite de la nota (contador sin exceso).
    expect(screen.getByTestId("block-word-count-coach-note").className).not.toMatch(/text-danger/);
  });

  it("el coach puede editar el aviso y «Guardar» llama a onSaveCoachNote con SU versión", () => {
    const { onSaveCoachNote } = setup({ stageLog: emptyNote() });
    fireEvent.click(screen.getByTestId("change-notice-insert"));
    fireEvent.change(screen.getByLabelText("Editar Nota del entrenador"), {
      target: { value: `${CHANGE_NOTICE_TEXT} Cualquier duda, escríbeme.` },
    });
    fireEvent.click(screen.getByTestId("block-save-coach-note"));
    expect(onSaveCoachNote).toHaveBeenCalledTimes(1);
    expect(onSaveCoachNote).toHaveBeenCalledWith(
      `${CHANGE_NOTICE_TEXT} Cualquier duda, escríbeme.`,
    );
  });

  it("«Guardar» sin tocar el texto guarda el aviso tal cual (≤60 palabras)", () => {
    const { onSaveCoachNote } = setup({ stageLog: emptyNote() });
    fireEvent.click(screen.getByTestId("change-notice-insert"));
    fireEvent.click(screen.getByTestId("block-save-coach-note"));
    expect(onSaveCoachNote).toHaveBeenCalledWith(CHANGE_NOTICE_TEXT);
  });

  it("Cancelar el editor no guarda nada y la oferta sigue disponible (no se insertó)", () => {
    const { onSaveCoachNote } = setup({ stageLog: emptyNote() });
    fireEvent.click(screen.getByTestId("change-notice-insert"));
    fireEvent.click(within(screen.getByTestId("block-card-coach-note")).getByRole("button", { name: "Cancelar" }));
    expect(onSaveCoachNote).not.toHaveBeenCalled();
    expect(screen.getByTestId("change-notice-offer")).toBeInTheDocument();
  });

  it("«No mostrar más» oculta la oferta y la recuerda por coach en localStorage", () => {
    setup({ stageLog: emptyNote() });
    fireEvent.click(screen.getByTestId("change-notice-dismiss"));
    expect(screen.queryByTestId("change-notice-offer")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("tyr:045-notice-dismissed:v1:7")).toBe("1");
  });

  it("un descarte previo del mismo coach mantiene la oferta oculta al volver a montar", () => {
    window.localStorage.setItem("tyr:045-notice-dismissed:v1:7", "1");
    setup({ stageLog: emptyNote() });
    expect(screen.queryByTestId("change-notice-offer")).not.toBeInTheDocument();
  });

  it("el descarte de otro coach no afecta a este", () => {
    window.localStorage.setItem("tyr:045-notice-dismissed:v1:99", "1");
    setup({ stageLog: emptyNote() });
    expect(screen.getByTestId("change-notice-offer")).toBeInTheDocument();
  });

  it("no ofrece nada si la nota ya tiene contenido (no pisa lo escrito por el coach)", () => {
    setup({ stageLog: buildStageLogFullMonth({ coach_note: "Gran mes de constancia." }) });
    expect(screen.queryByTestId("change-notice-offer")).not.toBeInTheDocument();
  });

  it("no ofrece nada si el coach ocultó la nota del entrenador", () => {
    setup({ stageLog: emptyNote(), hiddenBlocks: ["coach_note"] });
    expect(screen.queryByTestId("change-notice-offer")).not.toBeInTheDocument();
  });

  it("sin sesión (sin clave por coach) no ofrece nada", () => {
    useAuthStore.setState({ user: null, isAuthenticated: false });
    setup({ stageLog: emptyNote() });
    expect(screen.queryByTestId("change-notice-offer")).not.toBeInTheDocument();
  });

  it("nunca envía el boletín ni guarda por sí sola: la oferta sólo renderiza, sin efectos", () => {
    const { onSaveCoachNote, onSaveBlock, onRegenerateClick, onHideToggle } = setup({
      stageLog: emptyNote(),
    });
    expect(onSaveCoachNote).not.toHaveBeenCalled();
    expect(onSaveBlock).not.toHaveBeenCalled();
    expect(onRegenerateClick).not.toHaveBeenCalled();
    expect(onHideToggle).not.toHaveBeenCalled();
  });

  it("sin violaciones jest-axe con la oferta visible", async () => {
    const { container } = render(
      <BlockPanel
        stageLog={emptyNote()}
        hiddenBlocks={[]}
        onSaveBlock={() => {}}
        onSaveCoachNote={() => {}}
        onRegenerateClick={() => {}}
        onHideToggle={() => {}}
        onScrollToBlock={() => {}}
      />,
    );
    expect(screen.getByTestId("change-notice-offer")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones jest-axe con el editor abierto y el aviso pre-escrito", async () => {
    const { container } = render(
      <BlockPanel
        stageLog={emptyNote()}
        hiddenBlocks={[]}
        onSaveBlock={() => {}}
        onSaveCoachNote={() => {}}
        onRegenerateClick={() => {}}
        onHideToggle={() => {}}
        onScrollToBlock={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("change-notice-insert"));
    expect(await axe(container)).toHaveNoViolations();
  });
});
