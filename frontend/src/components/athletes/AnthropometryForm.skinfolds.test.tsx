/**
 * Tests — AnthropometryForm, segunda salida "Guardar y agregar pliegues"
 * (feature 046, US1, T031). Datos sintéticos; sin nombres.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/athletes", () => ({
  createAnthropometry: vi.fn(),
  getAnthropometry: vi.fn(),
}));

vi.mock("@/api/bodyComposition", () => ({
  getBodyComposition: vi.fn(),
}));

import * as athletesApi from "@/api/athletes";
import * as bodyCompositionApi from "@/api/bodyComposition";
import { AnthropometryForm } from "./AnthropometryForm";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { BodyCompositionOut } from "@/types/bodyComposition.types";
import { MaturationStatus, Sex } from "@/types/enums";

const CREATED_ID = 99;

const createdRecord = {
  id: CREATED_ID,
  athlete_id: 1,
  evaluation_date: "2026-01-15",
  weight_kg: 45,
  standing_height_cm: 155,
  arm_span_cm: null,
  sitting_height_cm: 73,
  leg_length_cm: 82,
  leg_sitting_ratio: 1.12,
  maturity_offset: -0.5,
  age_at_phv: 13.1,
  maturation_status: MaturationStatus.CircaPHV,
  training_implications: null,
  evaluated_by: 1,
  created_at: "2026-01-15T00:00:00Z",
  notes: null,
} as AnthropometricRecord;

function bodyComposition(nextDueDate: string | null): BodyCompositionOut {
  return {
    athlete_id: 1,
    sets: [],
    series: null,
    reading: null,
    estimates_latest: null,
    reference: null,
    next_due_date: nextDueDate,
  };
}

function renderForm(
  props: Partial<React.ComponentProps<typeof AnthropometryForm>> = {},
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onSuccess = vi.fn();
  const onAddSkinfolds = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <AnthropometryForm
        athleteId={1}
        athleteSex={Sex.M}
        athleteBirthDate="2013-06-15"
        onSuccess={onSuccess}
        onAddSkinfolds={onAddSkinfolds}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onSuccess, onAddSkinfolds };
}

function fillValidMeasurement(date = "2026-01-15") {
  const dateInput = document.querySelector("input[type='date']") as HTMLInputElement;
  fireEvent.change(dateInput, { target: { value: date } });
  const numInputs = document.querySelectorAll("input[type='number']");
  fireEvent.change(numInputs[0], { target: { valueAsNumber: 45 } });
  fireEvent.change(numInputs[1], { target: { valueAsNumber: 155 } });
  fireEvent.change(numInputs[3], { target: { valueAsNumber: 73 } });
}

beforeEach(() => {
  vi.mocked(athletesApi.createAnthropometry).mockReset();
  vi.mocked(bodyCompositionApi.getBodyComposition).mockReset();
});

describe("AnthropometryForm — salida de pliegues (T031)", () => {
  it("muestra 'Guardar y terminar' y 'Guardar y agregar pliegues' cuando no hay bloqueo", async () => {
    vi.mocked(bodyCompositionApi.getBodyComposition).mockResolvedValue(bodyComposition(null));
    renderForm();
    fillValidMeasurement();

    expect(
      await screen.findByRole("button", { name: "Guardar y agregar pliegues" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar y terminar" })).toBeInTheDocument();
  });

  it("'Guardar y agregar pliegues' guarda y entrega el id de la evaluación creada", async () => {
    vi.mocked(bodyCompositionApi.getBodyComposition).mockResolvedValue(bodyComposition(null));
    vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(createdRecord);
    const { onSuccess, onAddSkinfolds } = renderForm();
    fillValidMeasurement();

    await userEvent.click(
      await screen.findByRole("button", { name: "Guardar y agregar pliegues" }),
    );

    await waitFor(() => expect(onAddSkinfolds).toHaveBeenCalledWith(CREATED_ID));
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("'Guardar y terminar' conserva el comportamiento de siempre", async () => {
    vi.mocked(bodyCompositionApi.getBodyComposition).mockResolvedValue(bodyComposition(null));
    vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(createdRecord);
    const { onSuccess, onAddSkinfolds } = renderForm();
    fillValidMeasurement();

    await userEvent.click(await screen.findByRole("button", { name: "Guardar y terminar" }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(onAddSkinfolds).not.toHaveBeenCalled();
  });

  it("oculta la salida de pliegues cuando el intervalo mínimo la bloquea y explica desde cuándo", async () => {
    vi.mocked(bodyCompositionApi.getBodyComposition).mockResolvedValue(
      bodyComposition("2026-03-01"),
    );
    renderForm();
    fillValidMeasurement("2026-01-15");

    expect(await screen.findByTestId("skinfolds-interval-note")).toHaveTextContent(
      /la próxima toma puede hacerse desde el/,
    );
    expect(
      screen.queryByRole("button", { name: "Guardar y agregar pliegues" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar medición" })).toBeInTheDocument();
  });

  it("oculta la salida de pliegues cuando el deportista tiene menos de 9 años en la fecha", async () => {
    vi.mocked(bodyCompositionApi.getBodyComposition).mockResolvedValue(bodyComposition(null));
    renderForm({ athleteBirthDate: "2018-06-15" });
    fillValidMeasurement("2026-01-15");

    await waitFor(() =>
      expect(bodyCompositionApi.getBodyComposition).toHaveBeenCalled(),
    );
    expect(
      screen.queryByRole("button", { name: "Guardar y agregar pliegues" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("skinfolds-interval-note")).not.toBeInTheDocument();
  });

  it("sin onAddSkinfolds no consulta composición corporal ni muestra la salida", () => {
    renderForm({ onAddSkinfolds: undefined });
    expect(screen.getByRole("button", { name: "Guardar medición" })).toBeInTheDocument();
    expect(bodyCompositionApi.getBodyComposition).not.toHaveBeenCalled();
  });
});
