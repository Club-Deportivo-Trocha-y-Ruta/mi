import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
  // Usado por `useCancelRun` (acción "Descartar análisis"). Su flujo se
  // prueba con MSW en `HITLApprovalCard.cancel.test.tsx`; aquí sólo hace
  // falta que el export exista para no romper el mock del módulo.
  cancelRun: vi.fn(),
}));

import * as raceApi from "@/api/raceAnalysis";

import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

const ACK = {
  accepted: true,
  run_id: "r1",
  step_id: "hitl_1",
  next_state: "running" as const,
};

describe("HITLApprovalCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renderiza draft + acciones aprobar/editar/rechazar", () => {
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="# Draft de prueba"
      />,
    );
    expect(screen.getByRole("region", { name: /revisión humana/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Draft de prueba" })).toBeInTheDocument();
    expect(screen.getByTestId("hitl-approve-button")).toBeInTheDocument();
    expect(screen.getByTestId("hitl-edit-button")).toBeInTheDocument();
    expect(screen.getByTestId("hitl-reject-button")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------
  // Decisión 2026-09-23: aprobar un insight ya NO envía correo automático
  // a los padres (solo lo publica en la app). El botón "Aprobar" debe
  // dejarlo explícito junto a la acción, y seguir cumpliendo el touch
  // target mínimo de 48px (constitución III).
  // -------------------------------------------------------------------
  it("muestra la nota de que aprobar no envía correo, junto al botón Aprobar", () => {
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="texto" />,
    );
    expect(
      screen.getByTestId("hitl-approve-no-email-note"),
    ).toHaveTextContent(
      "Al aprobar, la familia podrá verlo en la app. No se envía correo.",
    );
  });

  it("el botón Aprobar cumple el touch target mínimo de 48px", () => {
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="texto" />,
    );
    expect(screen.getByTestId("hitl-approve-button").className).toMatch(
      /min-h-12/,
    );
  });

  it("Aprobar dispara mutation con decision=approve", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue(ACK);
    const onSubmitted = vi.fn();
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="texto"
        onSubmitted={onSubmitted}
      />,
    );
    await userEvent.setup().click(screen.getByTestId("hitl-approve-button"));
    await waitFor(() =>
      expect(raceApi.submitHITLDecision).toHaveBeenCalledWith(
        "r1",
        "hitl_1",
        { decision: "approve" },
      ),
    );
    expect(onSubmitted).toHaveBeenCalledWith("approve");
  });

  it("Rechazar incluye notes opcionales", async () => {
    const user = userEvent.setup();
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue(ACK);
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
    );
    await user.type(
      screen.getByTestId("hitl-reject-notes-input"),
      "No cumple principios LTAD",
    );
    await user.click(screen.getByTestId("hitl-reject-button"));
    await waitFor(() =>
      expect(raceApi.submitHITLDecision).toHaveBeenCalledWith(
        "r1",
        "hitl_1",
        { decision: "reject", notes: "No cumple principios LTAD" },
      ),
    );
  });

  it("muestra feedback del crítico cuando se provee", () => {
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="t"
        criticFeedback={[
          { section: "Recomendaciones", problem: "Sin evidencia LTAD" },
        ]}
      />,
    );
    expect(screen.getByTestId("hitl-critic-feedback")).toBeInTheDocument();
    expect(screen.getByText(/Sin evidencia LTAD/)).toBeInTheDocument();
  });

  // Feature 045 (T051, FR-002): el resumen del feedback se llama «Revisión
  // automática»; «Crítico LLM dice» es jerga retirada del glosario.
  it("el resumen del feedback dice «Revisión automática (N)», nunca «Crítico LLM dice»", () => {
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="t"
        criticFeedback={[
          { section: "Recomendaciones", problem: "Sin evidencia LTAD" },
          { problem: "Tono demasiado técnico" },
        ]}
      />,
    );
    expect(screen.getByText("Revisión automática (2)")).toBeInTheDocument();
    expect(screen.queryByText(/Crítico LLM/i)).not.toBeInTheDocument();
  });

  // Feature 045 (T051, FR-019/constitución III): Editar y Rechazar llegan a
  // 48 px como Aprobar y Descartar (el botón por defecto queda en ~36-44 px).
  it.each([
    ["hitl-edit-button", "Editar"],
    ["hitl-reject-button", "Rechazar"],
    ["hitl-discard-button", "Descartar análisis"],
  ])("el botón %s (%s) cumple el touch target mínimo de 48px", (testId) => {
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="texto" />,
    );
    expect(screen.getByTestId(testId).className).toMatch(/min-h-12/);
  });

  // Feature 045 (T062, FR-022): aviso cuando el borrador menciona la brecha
  // con el primer lugar o el podio en el texto que verá la familia. Es
  // informativo — Aprobar y Rechazar siguen disponibles.
  describe("aviso de brecha con el podio (family_gap_mentions, T062)", () => {
    const WARNING =
      "Este análisis menciona la brecha con el primer lugar o el podio, y la familia lo verá. Puedes aprobarlo igual o pedir una revisión.";

    it("con fragmentos muestra el aviso del contrato y cada fragmento", () => {
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="texto"
          familyGapMentions={[
            "terminó a 40 s del ganador",
            "quedó lejos del podio",
          ]}
        />,
      );
      const warning = screen.getByTestId("hitl-family-gap-warning");
      expect(warning).toHaveTextContent(WARNING);
      const snippets = screen.getByRole("list", {
        name: "Fragmentos que mencionan la brecha",
      });
      expect(snippets).toHaveTextContent("«terminó a 40 s del ganador»");
      expect(snippets).toHaveTextContent("«quedó lejos del podio»");
      expect(screen.getAllByRole("listitem")).toHaveLength(2);
    });

    it.each([
      ["lista vacía", []],
      ["prop ausente", undefined],
    ])("%s: no hay aviso", (_label, mentions) => {
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="texto"
          familyGapMentions={mentions}
        />,
      );
      expect(screen.queryByTestId("hitl-family-gap-warning")).not.toBeInTheDocument();
      expect(screen.queryByText(/brecha con el primer lugar/i)).not.toBeInTheDocument();
    });

    it("Aprobar y Rechazar siguen disponibles y funcionan con el aviso visible", async () => {
      vi.mocked(raceApi.submitHITLDecision).mockResolvedValue(ACK);
      const user = userEvent.setup();
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="texto"
          familyGapMentions={["terminó a 40 s del ganador"]}
        />,
      );
      expect(screen.getByTestId("hitl-family-gap-warning")).toBeInTheDocument();
      expect(screen.getByTestId("hitl-approve-button")).toBeEnabled();
      expect(screen.getByTestId("hitl-reject-button")).toBeEnabled();

      await user.click(screen.getByTestId("hitl-approve-button"));
      await waitFor(() =>
        expect(raceApi.submitHITLDecision).toHaveBeenCalledWith("r1", "hitl_1", {
          decision: "approve",
        }),
      );
    });

    it("sin violaciones jest-axe con el aviso visible", async () => {
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="# Draft de prueba"
          criticFeedback={[{ problem: "Sin evidencia LTAD" }]}
          familyGapMentions={["terminó a 40 s del ganador", "lejos del podio"]}
        />,
      );
      expect(await axe(document.body)).toHaveNoViolations();
    });
  });

  it("muestra error cuando la mutation falla", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
      new Error("422 invalid edits"),
    );
    const user = userEvent.setup();
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
    );
    await user.click(screen.getByTestId("hitl-approve-button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /422 invalid edits/i,
    );
  });

  // ---------------------------------------------------------------------
  // T079 (feature 036, US7) — flujo completo de "Editar": abrir diálogo,
  // escribir, guardar y cancelar. Antes de este bloque,
  // `HITLApprovalCard.test.tsx` sólo probaba que el botón "Editar" EXISTE
  // (arriba, "renderiza draft + acciones..."), nunca lo clickeaba — borrar
  // el `onClick` de `handleSaveEdit`/`setEditOpen(true)` en el componente
  // habría dejado la suite en verde. Estos tests fallan si se rompe
  // cualquiera de los dos.
  // ---------------------------------------------------------------------
  describe("flujo Editar (T079)", () => {
    it("abre el diálogo con el markdown del draft pre-cargado en el textarea", async () => {
      const user = userEvent.setup();
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="# Borrador original"
        />,
      );

      // El diálogo no está montado hasta que se abre.
      expect(screen.queryByTestId("hitl-edit-textarea")).not.toBeInTheDocument();

      await user.click(screen.getByTestId("hitl-edit-button"));

      const textarea = await screen.findByTestId("hitl-edit-textarea");
      expect(textarea).toHaveValue("# Borrador original");
    });

    // Feature 045 (T078, FR-063 / SC-010): touch target mínimo de 48 px en el
    // pie del diálogo de edición.
    it("los botones «Cancelar» y «Guardar y aprobar» del diálogo cumplen min-h-12", async () => {
      const user = userEvent.setup();
      wrap(
        <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="Original" />,
      );

      await user.click(screen.getByTestId("hitl-edit-button"));
      await screen.findByTestId("hitl-edit-textarea");

      expect(screen.getByRole("button", { name: "Cancelar" }).className).toMatch(
        /min-h-12/,
      );
      expect(screen.getByTestId("hitl-edit-save-button").className).toMatch(
        /min-h-12/,
      );
    });

    it("escribe una edición y Guardar y aprobar envía decision=edit con el markdown editado, y cierra el diálogo", async () => {
      const user = userEvent.setup();
      vi.mocked(raceApi.submitHITLDecision).mockResolvedValue(ACK);
      const onSubmitted = vi.fn();
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="Original"
          onSubmitted={onSubmitted}
        />,
      );

      await user.click(screen.getByTestId("hitl-edit-button"));
      const textarea = await screen.findByTestId("hitl-edit-textarea");

      await user.clear(textarea);
      await user.type(textarea, "Texto corregido por el coach");

      await user.click(screen.getByTestId("hitl-edit-save-button"));

      await waitFor(() =>
        expect(raceApi.submitHITLDecision).toHaveBeenCalledWith("r1", "hitl_1", {
          decision: "edit",
          edits: "Texto corregido por el coach",
        }),
      );
      expect(onSubmitted).toHaveBeenCalledWith("edit");

      // El diálogo se cierra tras un guardado exitoso.
      await waitFor(() =>
        expect(screen.queryByTestId("hitl-edit-textarea")).not.toBeInTheDocument(),
      );
    });

    it("Cancelar cierra el diálogo sin enviar ninguna decisión", async () => {
      const user = userEvent.setup();
      wrap(
        <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="Original" />,
      );

      await user.click(screen.getByTestId("hitl-edit-button"));
      const textarea = await screen.findByTestId("hitl-edit-textarea");
      await user.type(textarea, " — nota que no debe enviarse");

      await user.click(screen.getByRole("button", { name: "Cancelar" }));

      await waitFor(() =>
        expect(screen.queryByTestId("hitl-edit-textarea")).not.toBeInTheDocument(),
      );
      expect(raceApi.submitHITLDecision).not.toHaveBeenCalled();
    });

    it("si Guardar y aprobar falla, el diálogo permanece abierto y muestra el error", async () => {
      const user = userEvent.setup();
      vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
        new Error("409 conflict"),
      );
      wrap(
        <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="Original" />,
      );

      await user.click(screen.getByTestId("hitl-edit-button"));
      const textarea = await screen.findByTestId("hitl-edit-textarea");
      await user.type(textarea, " editado");
      await user.click(screen.getByTestId("hitl-edit-save-button"));

      // El error se muestra DENTRO del diálogo (el banner de la sección
      // principal queda aria-hidden/detrás del overlay mientras el diálogo
      // está abierto, así que ese no serviría para que el coach lo vea).
      expect(await screen.findByTestId("hitl-edit-dialog-error")).toHaveTextContent(
        /409 conflict/i,
      );
      // El diálogo NO se cierra cuando falla — el coach no pierde su edición.
      expect(screen.getByTestId("hitl-edit-textarea")).toBeInTheDocument();
    });
  });

  it("409 (el run ya no espera aprobación) muestra un mensaje claro, no el error crudo de axios", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
      Object.assign(new Error("Request failed with status code 409"), {
        response: { status: 409 },
      }),
    );
    wrap(<HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="texto" />);
    await userEvent.setup().click(screen.getByTestId("hitl-approve-button"));
    expect(
      await screen.findByText(/ya no está esperando aprobación/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/status code 409/i)).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // T094 (feature 036, US6) — HITLApprovalCard es un componente con diálogo
  // y no tenía ningún chequeo jest-axe en ningún archivo de test. Cubrimos
  // el estado de reposo y el diálogo de edición abierto (el caso que un
  // check solo-en-reposo se saltaría por completo).
  //
  // `axe(document.body)` en vez de `axe(container)` — mismo patrón que
  // ConfirmDialog.test.tsx / LinkSessionDialog.test.tsx / etc.: Radix
  // `Dialog` renderiza `DialogContent` en un portal a `document.body`, fuera
  // del `container` que devuelve `render()`, así que `axe(container)` no
  // vería el diálogo abierto.
  // ---------------------------------------------------------------------
  describe("accesibilidad (T094)", () => {
    it("sin violaciones a11y en estado de reposo", async () => {
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="# Draft de prueba"
          criticFeedback={[
            { section: "Recomendaciones", problem: "Sin evidencia LTAD" },
          ]}
        />,
      );
      expect(await axe(document.body)).toHaveNoViolations();
    });

    it("sin violaciones a11y con el diálogo de edición abierto", async () => {
      const user = userEvent.setup();
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="# Draft de prueba"
        />,
      );
      await user.click(screen.getByTestId("hitl-edit-button"));
      await waitFor(() => {
        expect(screen.getByTestId("hitl-edit-textarea")).toBeInTheDocument();
      });
      expect(await axe(document.body)).toHaveNoViolations();
    });

    it("sin violaciones a11y con el diálogo abierto y un error de guardado visible (T079)", async () => {
      const user = userEvent.setup();
      vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
        new Error("409 conflict"),
      );
      wrap(
        <HITLApprovalCard
          runId="r1"
          stepId="hitl_1"
          draftMarkdown="# Draft de prueba"
        />,
      );
      await user.click(screen.getByTestId("hitl-edit-button"));
      await user.click(screen.getByTestId("hitl-edit-save-button"));
      expect(await screen.findByTestId("hitl-edit-dialog-error")).toBeInTheDocument();
      expect(await axe(document.body)).toHaveNoViolations();
    });
  });
});
