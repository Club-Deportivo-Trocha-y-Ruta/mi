import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import {
  makeAnthropometricRecord,
  plausibilityOkHandler,
  plausibilityWarningsHandler,
  sameDateConflictHandler,
} from "@/test/msw/anthropometryHandlers";
import { makeBodyCompositionOut } from "@/test/msw/bodyCompositionHandlers";
import { BENCH_HEIGHT_KEY, CAPTURE_MODE_KEY } from "@/lib/anthropometry/devicePrefs";
import type { AnthropometryCreate } from "@/types/anthropometry.types";
import { Sex } from "@/types/enums";

import {
  AnthropometryCapture,
  type AnthropometryCaptureProps,
} from "../AnthropometryCapture";

// Fixtures ficticias: sin nombres ni datos reales de menores.
const ATHLETE_ID = 17;
const BIRTH_12Y = "2014-03-01";
const BIRTH_8Y = "2019-01-01";

function bodyCompositionHandler(nextDue: string | null = null) {
  return http.get("*/api/athletes/:athleteId/body-composition", () =>
    HttpResponse.json(makeBodyCompositionOut({ athlete_id: ATHLETE_ID, next_due_date: nextDue })),
  );
}

function capturingCreateHandler(sink: AnthropometryCreate[], id = 901) {
  return http.post("*/api/athletes/:athleteId/anthropometry", async ({ request }) => {
    const body = (await request.json()) as AnthropometryCreate;
    sink.push(body);
    return HttpResponse.json(makeAnthropometricRecord({ ...body, id, arm_span_cm: null }), {
      status: 201,
    });
  });
}

function renderCapture(overrides: Partial<AnthropometryCaptureProps> = {}) {
  const onDone = vi.fn();
  const props: AnthropometryCaptureProps = {
    athlete: { id: ATHLETE_ID, sex: Sex.M, birth_date: BIRTH_12Y },
    onDone,
    ...overrides,
  };
  const utils = renderWithProviders(
    <Routes>
      <Route path="/capture" element={<AnthropometryCapture {...props} />} />
      <Route
        path="/athletes/:id/anthropometry/:recordId/edit"
        element={<p>Pantalla de edición</p>}
      />
      <Route path="/athletes/:id" element={<p>Perfil del deportista</p>} />
    </Routes>,
    { initialEntries: ["/capture"] },
  );
  return { ...utils, onDone, props };
}

/** Recorre el asistente guiado hasta «Revisar» (banco 40, lectura 112 → neta 72). */
async function walkGuided(user: UserEvent, { check }: { check?: () => Promise<void> } = {}) {
  expect(screen.getByRole("heading", { name: "Preparación" })).toBeInTheDocument();
  await check?.();
  await user.click(screen.getByRole("button", { name: "Empezar" }));

  expect(await screen.findByRole("heading", { name: "Peso" })).toBeInTheDocument();
  await check?.();
  await user.type(screen.getByLabelText("Peso (kg)"), "45,5");
  await user.click(screen.getByRole("button", { name: "Siguiente" }));

  expect(await screen.findByRole("heading", { name: "Talla de pie" })).toBeInTheDocument();
  await user.type(screen.getByLabelText("Talla de pie (cm)"), "150");
  await user.click(screen.getByRole("button", { name: "Siguiente" }));

  expect(await screen.findByRole("heading", { name: "Talla sentado" })).toBeInTheDocument();
  await user.type(screen.getByLabelText("Lectura en el tallímetro (cm)"), "112");
  const bench = screen.getByLabelText("Altura del banco (cm)");
  await user.clear(bench);
  await user.type(bench, "40");
  expect(screen.getByTestId("net-sitting-height")).toHaveTextContent("Talla sentado neta: 72,0 cm");
  await check?.();
  await user.click(screen.getByRole("button", { name: "Siguiente" }));

  expect(await screen.findByRole("heading", { name: "Envergadura" })).toBeInTheDocument();
  await check?.();
  await user.click(screen.getByRole("button", { name: "Omitir (opcional)" }));

  expect(await screen.findByRole("heading", { name: "Revisar" })).toBeInTheDocument();
}

describe("AnthropometryCapture", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("modo guiado de punta a punta: envía la talla neta (112 − 40 = 72) y guarda el banco; axe por paso", async () => {
    const sink: AnthropometryCreate[] = [];
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler(), capturingCreateHandler(sink));
    const user = userEvent.setup();
    const { container, onDone } = renderCapture();

    await walkGuided(user, {
      check: async () => {
        expect(await axe(container)).toHaveNoViolations();
      },
    });

    // Paso «Revisar»: sin avisos y con PHV; axe.
    await waitFor(() => expect(screen.queryByText("Revisando las medidas…")).not.toBeInTheDocument());
    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(onDone).toHaveBeenCalledWith(
      expect.objectContaining({ recordId: 901, intent: "finish" }),
    );
    expect(sink).toHaveLength(1);
    expect(sink[0]).toMatchObject({
      weight_kg: 45.5,
      standing_height_cm: 150,
      sitting_height_cm: 72,
      arm_span_cm: null,
    });
    expect(sink[0]).not.toHaveProperty("bench_height_cm");
    expect(window.localStorage.getItem(BENCH_HEIGHT_KEY)).toBe("40");
  });

  it("valida cada paso antes de avanzar", async () => {
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler());
    const user = userEvent.setup();
    renderCapture();

    await user.click(screen.getByRole("button", { name: "Empezar" }));
    await user.click(await screen.findByRole("button", { name: "Siguiente" }));
    expect(await screen.findByText("Obligatorio")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Peso" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Peso (kg)"), "10");
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByText("Mín. 20 kg")).toBeInTheDocument();
  });

  it("«Guardar y agregar pliegues» guarda y entrega el id con intent skinfolds (≥ 9 años)", async () => {
    const sink: AnthropometryCreate[] = [];
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler(), capturingCreateHandler(sink, 902));
    const user = userEvent.setup();
    const { onDone } = renderCapture();

    await walkGuided(user);
    await user.click(await screen.findByRole("button", { name: "Guardar y agregar pliegues" }));
    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith(
        expect.objectContaining({ recordId: 902, intent: "skinfolds" }),
      ),
    );
  });

  it("oculta «Guardar y agregar pliegues» si el deportista tiene menos de 9 años", async () => {
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler());
    const user = userEvent.setup();
    renderCapture({ athlete: { id: ATHLETE_ID, sex: Sex.F, birth_date: BIRTH_8Y } });

    await walkGuided(user);
    expect(screen.getByRole("button", { name: "Guardar y terminar" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Guardar y agregar pliegues" }),
    ).not.toBeInTheDocument();
  });

  it("«Volver a medir» salta al paso de esa medida", async () => {
    mswServer.use(
      plausibilityWarningsHandler([{ code: "sitting_ratio_atypical", measure: "sitting_height" }]),
      bodyCompositionHandler(),
    );
    const user = userEvent.setup();
    renderCapture();

    await walkGuided(user);
    await user.click(await screen.findByRole("button", { name: "Volver a medir" }));
    const heading = await screen.findByRole("heading", { name: "Talla sentado" });
    // El valor bruto sigue ahí para corregirlo.
    expect(screen.getByLabelText("Lectura en el tallímetro (cm)")).toHaveValue("112");
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("persiste el modo en el dispositivo y el modo rápido envía la talla neta", async () => {
    const sink: AnthropometryCreate[] = [];
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler(), capturingCreateHandler(sink));
    const user = userEvent.setup();
    const { container, onDone, unmount } = renderCapture();

    expect(screen.getByRole("radio", { name: "Guiado" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: "Rápido" }));
    expect(window.localStorage.getItem(CAPTURE_MODE_KEY)).toBe("quick");

    const form = screen.getByRole("form", { name: "Captura rápida de medición" });
    expect(await axe(container)).toHaveNoViolations();
    await user.type(within(form).getByLabelText("Peso (kg)"), "45,5");
    await user.type(within(form).getByLabelText("Talla de pie (cm)"), "150");
    await user.type(within(form).getByLabelText(/Lectura del tallímetro/), "112");
    const bench = within(form).getByLabelText("Altura del banco (cm)");
    await user.clear(bench);
    await user.type(bench, "40");
    await user.click(within(form).getByRole("button", { name: "Revisar y guardar" }));

    expect(await screen.findByRole("heading", { name: "Revisar" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Revisando las medidas…")).not.toBeInTheDocument());
    expect(await axe(container)).toHaveNoViolations();
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(sink[0]).toMatchObject({ sitting_height_cm: 72, standing_height_cm: 150 });

    unmount();
    renderCapture();
    expect(screen.getByRole("radio", { name: "Rápido" })).toHaveAttribute("aria-checked", "true");
  });

  it("409 misma fecha: diálogo; «Abrir la existente» va a la edición si puede modificarla", async () => {
    mswServer.use(
      plausibilityOkHandler,
      bodyCompositionHandler(),
      sameDateConflictHandler("post", { existingRecordId: 811, sameValues: false }),
      http.get("*/api/athletes/:athleteId/anthropometry", () =>
        HttpResponse.json([makeAnthropometricRecord({ id: 811, can_modify: true })]),
      ),
    );
    const user = userEvent.setup();
    const { onDone } = renderCapture();

    await walkGuided(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Ya existe una medición de esta fecha")).toBeInTheDocument();
    expect(await axe(dialog)).toHaveNoViolations();
    expect(onDone).not.toHaveBeenCalled();

    // Espera a conocer `can_modify` del registro existente.
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Abrir la existente" })).toBeEnabled(),
    );
    await user.click(within(dialog).getByRole("button", { name: "Abrir la existente" }));
    expect(await screen.findByText("Pantalla de edición")).toBeInTheDocument();
  });

  it("409 misma fecha sin permiso: «Abrir la existente» va al historial", async () => {
    mswServer.use(
      plausibilityOkHandler,
      bodyCompositionHandler(),
      sameDateConflictHandler("post", { existingRecordId: 811, sameValues: false }),
      http.get("*/api/athletes/:athleteId/anthropometry", () =>
        HttpResponse.json([makeAnthropometricRecord({ id: 811, can_modify: false })]),
      ),
    );
    const user = userEvent.setup();
    renderCapture();

    await walkGuided(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    const dialog = await screen.findByRole("alertdialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Abrir la existente" })).toBeEnabled(),
    );
    await user.click(within(dialog).getByRole("button", { name: "Abrir la existente" }));
    expect(await screen.findByText("Perfil del deportista")).toBeInTheDocument();
  });

  it("409 misma fecha: «Cambiar la fecha» vuelve a Preparación", async () => {
    mswServer.use(
      plausibilityOkHandler,
      bodyCompositionHandler(),
      sameDateConflictHandler("post", { existingRecordId: 811, sameValues: false }),
      http.get("*/api/athletes/:athleteId/anthropometry", () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderCapture();

    await walkGuided(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Cambiar la fecha" }));
    expect(await screen.findByRole("heading", { name: "Preparación" })).toBeInTheDocument();
    expect(screen.getByLabelText("Fecha de la medición")).toBeEnabled();
    await waitFor(() => expect(screen.getByLabelText("Fecha de la medición")).toHaveFocus());
  });

  it("409 misma fecha: Escape lleva el foco al campo de fecha (Preparación en guiado)", async () => {
    mswServer.use(
      plausibilityOkHandler,
      bodyCompositionHandler(),
      sameDateConflictHandler("post", { existingRecordId: 811, sameValues: false }),
      http.get("*/api/athletes/:athleteId/anthropometry", () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderCapture();

    await walkGuided(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    await screen.findByRole("alertdialog");
    await user.keyboard("{Escape}");
    expect(await screen.findByRole("heading", { name: "Preparación" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Fecha de la medición")).toHaveFocus());
  });

  it("los valores sobreviven al cambiar de modo en ambos sentidos", async () => {
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler());
    const user = userEvent.setup();
    renderCapture();

    // Guiado -> Rápido
    await user.click(screen.getByRole("button", { name: "Empezar" }));
    await user.type(await screen.findByLabelText("Peso (kg)"), "45,5");
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await user.type(await screen.findByLabelText("Talla de pie (cm)"), "150");
    await user.click(screen.getByRole("radio", { name: "Rápido" }));
    let form = screen.getByRole("form", { name: "Captura rápida de medición" });
    expect(within(form).getByLabelText("Peso (kg)")).toHaveValue("45,5");
    expect(within(form).getByLabelText("Talla de pie (cm)")).toHaveValue("150");

    // Rápido -> Guiado (sin pasar por «Revisar»)
    await user.type(within(form).getByLabelText(/Lectura del tallímetro/), "112");
    await user.click(screen.getByRole("radio", { name: "Guiado" }));
    await user.click(screen.getByRole("button", { name: "Empezar" }));
    expect(await screen.findByLabelText("Peso (kg)")).toHaveValue("45,5");
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByLabelText("Talla de pie (cm)")).toHaveValue("150");
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByLabelText("Lectura en el tallímetro (cm)")).toHaveValue("112");

    // y de vuelta a Rápido conserva todo
    await user.click(screen.getByRole("radio", { name: "Rápido" }));
    form = screen.getByRole("form", { name: "Captura rápida de medición" });
    expect(within(form).getByLabelText(/Lectura del tallímetro/)).toHaveValue("112");
  });

  it("con fecha bloqueada (jornada) el campo de fecha no se puede cambiar", () => {
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler());
    renderCapture({ lockedDate: "2026-09-01" });
    const date = screen.getByLabelText("Fecha de la medición");
    expect(date).toHaveValue("2026-09-01");
    expect(date).toBeDisabled();
  });
});
