/**
 * Tests de CoachAnswerForm (feature 037, T205).
 */
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";

import { CoachAnswerForm } from "@/components/athletes/ai/CoachAnswerForm";
import { mswServer } from "@/test/setup";
import {
  answerInsightSuccessHandler,
  answerInsightEmptyBodyHandler,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { mockInsightV3Detail } from "@/test/fixtures/insightV3";

const ATHLETE_ID = 7;
const INSIGHT_ID = 2001;

function renderForm(props?: Partial<React.ComponentProps<typeof CoachAnswerForm>>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CoachAnswerForm athleteId={ATHLETE_ID} insightId={INSIGHT_ID} {...props} />
    </QueryClientProvider>,
  );
}

describe("CoachAnswerForm", () => {
  it("no tiene violaciones de accesibilidad", async () => {
    mswServer.use(answerInsightSuccessHandler((o) => mockInsightV3Detail(o)));
    const { container } = renderForm();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("muestra el contador de caracteres y respeta el máximo de 1000", async () => {
    renderForm();
    const textarea = screen.getByLabelText("Tu respuesta");
    expect(screen.getByText("0/1000")).toBeInTheDocument();
    await userEvent.type(textarea, "Hola");
    expect(screen.getByText("4/1000")).toBeInTheDocument();
    expect(textarea).toHaveAttribute("maxlength", "1000");
  });

  it("envía el texto y muestra confirmación de guardado", async () => {
    mswServer.use(answerInsightSuccessHandler((o) => mockInsightV3Detail(o)));
    renderForm();

    const textarea = screen.getByLabelText("Tu respuesta");
    await userEvent.type(textarea, "Se sintió cómodo en el tramo técnico.");
    await userEvent.click(screen.getByRole("button", { name: "Guardar respuesta" }));

    await waitFor(() => {
      expect(screen.getByText("Respuesta guardada.")).toBeInTheDocument();
    });
  });

  it("los botones de calificación son accesibles con aria-pressed y alternan estado", async () => {
    mswServer.use(answerInsightSuccessHandler((o) => mockInsightV3Detail(o)));
    renderForm();

    const usefulBtn = screen.getByRole("button", { name: "Marcar insight como útil" });
    expect(usefulBtn).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(usefulBtn);
    await waitFor(() => expect(usefulBtn).toHaveAttribute("aria-pressed", "true"));

    const notUsefulBtn = screen.getByRole("button", {
      name: "Marcar insight como no útil",
    });
    expect(notUsefulBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("muestra el error del servidor cuando la calificación falla", async () => {
    mswServer.use(answerInsightEmptyBodyHandler);
    renderForm();

    const usefulBtn = screen.getByRole("button", { name: "Marcar insight como útil" });
    await userEvent.click(usefulBtn);

    await waitFor(() => {
      expect(
        screen.getByText("Debe enviar answer_text y/o rating."),
      ).toBeInTheDocument();
    });
  });

  it("precarga valores iniciales de respuesta y calificación", () => {
    renderForm({ initialAnswer: "Respuesta previa.", initialRating: 1 });
    expect(screen.getByLabelText("Tu respuesta")).toHaveValue("Respuesta previa.");
    expect(
      screen.getByRole("button", { name: "Marcar insight como útil" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});
