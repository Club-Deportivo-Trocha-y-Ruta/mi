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
