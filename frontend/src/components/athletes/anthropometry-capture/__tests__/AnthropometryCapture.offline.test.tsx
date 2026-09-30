import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import {
  makeAnthropometricRecord,
  plausibilityOkHandler,
} from "@/test/msw/anthropometryHandlers";
import { makeBodyCompositionOut } from "@/test/msw/bodyCompositionHandlers";
import { CAPTURE_MODE_KEY } from "@/lib/anthropometry/devicePrefs";
import { Sex } from "@/types/enums";

import { AnthropometryCapture } from "../AnthropometryCapture";

// Fixtures ficticias: sin nombres ni datos reales de menores.
const ATHLETE_ID = 17;
const COLLECTION = "*/api/athletes/:athleteId/anthropometry";
const OFFLINE_SAVE = "Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.";

function bodyCompositionHandler() {
  return http.get("*/api/athletes/:athleteId/body-composition", () =>
    HttpResponse.json(makeBodyCompositionOut({ athlete_id: ATHLETE_ID, next_due_date: null })),
  );
}

/** POST que responde, en orden, cada entrada de `responses` (la última se repite). */
function sequencedCreateHandler(responses: (() => Response)[], calls: { count: number }) {
  return http.post(COLLECTION, () => {
    const index = Math.min(calls.count, responses.length - 1);
    calls.count += 1;
    return responses[index]();
  });
}

const networkError = () => HttpResponse.error();
const sameDate = (sameValues: boolean) => () =>
  HttpResponse.json(
    { detail: "anthropometry_same_date_exists", existing_record_id: 811, same_values: sameValues },
    { status: 409 },
  );

function renderCapture() {
  const onDone = vi.fn();
  const utils = renderWithProviders(
    <AnthropometryCapture
      athlete={{ id: ATHLETE_ID, sex: Sex.M, birth_date: "2014-03-01" }}
      onDone={onDone}
    />,
  );
  return { ...utils, onDone };
}

/** Captura rápida hasta el panel «Revisar» (lectura 112, banco 40). */
async function fillQuickAndReview(user: UserEvent) {
  const form = screen.getByRole("form", { name: "Captura rápida de medición" });
  await user.type(within(form).getByLabelText("Peso (kg)"), "45,5");
  await user.type(within(form).getByLabelText("Talla de pie (cm)"), "150");
  await user.type(within(form).getByLabelText(/Lectura del tallímetro/), "112");
  const bench = within(form).getByLabelText("Altura del banco (cm)");
  await user.clear(bench);
  await user.type(bench, "40");
  await user.click(within(form).getByRole("button", { name: "Revisar y guardar" }));
  await screen.findByRole("heading", { name: "Revisar" });
}

describe("AnthropometryCapture — sin conexión y reintento (T049)", () => {
  const originalOnLine = Object.getOwnPropertyDescriptor(window.navigator, "onLine");

  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(CAPTURE_MODE_KEY, "quick");
    mswServer.use(plausibilityOkHandler, bodyCompositionHandler());
  });
  afterEach(() => {
    window.localStorage.clear();
    if (originalOnLine) {
      Object.defineProperty(window.navigator, "onLine", originalOnLine);
    } else {
      delete (window.navigator as { onLine?: boolean }).onLine;
    }
  });

  it("al abrir sin conexión avisa y deshabilita «Empezar»", async () => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, get: () => false });
    window.localStorage.setItem(CAPTURE_MODE_KEY, "guided");
    const { container } = renderCapture();

    expect(
      screen.getByText("Necesitas conexión a internet para registrar mediciones."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Empezar" })).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("un error de red muestra el banner con «Reintentar» y conserva los valores", async () => {
    const calls = { count: 0 };
    mswServer.use(sequencedCreateHandler([networkError], calls));
    const user = userEvent.setup();
    const { container, onDone } = renderCapture();

    await fillQuickAndReview(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));

    const alert = await screen.findByText(OFFLINE_SAVE);
    expect(alert).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
    // Los valores siguen en pantalla (tabla del panel «Revisar» y la cuadrícula).
    expect(screen.getAllByText("72,0 cm").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Peso (kg)")).toHaveValue("45,5");
    await waitFor(() => expect(screen.queryByText("Revisando las medidas…")).not.toBeInTheDocument());
    expect(await axe(container)).toHaveNoViolations();
  });

  it("reintento tras respuesta perdida → 409 same_values:true cuenta como guardado, una sola vez", async () => {
    const calls = { count: 0 };
    mswServer.use(sequencedCreateHandler([networkError, sameDate(true)], calls));
    const user = userEvent.setup();
    const { onDone } = renderCapture();

    await fillQuickAndReview(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    await user.click(await screen.findByRole("button", { name: "Reintentar" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(onDone).toHaveBeenCalledWith(
      expect.objectContaining({ recordId: 811, intent: "finish", alreadySaved: true }),
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(calls.count).toBe(2);
  });

  it("el reintento conserva la salida elegida (pliegues)", async () => {
    const calls = { count: 0 };
    mswServer.use(
      sequencedCreateHandler(
        [networkError, () => HttpResponse.json(makeAnthropometricRecord({ id: 905 }), { status: 201 })],
        calls,
      ),
    );
    const user = userEvent.setup();
    const { onDone } = renderCapture();

    await fillQuickAndReview(user);
    await user.click(await screen.findByRole("button", { name: "Guardar y agregar pliegues" }));
    await user.click(await screen.findByRole("button", { name: "Reintentar" }));
    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith(
        expect.objectContaining({ recordId: 905, intent: "skinfolds" }),
      ),
    );
  });

  it("409 same_values:false en el primer intento → diálogo, no éxito", async () => {
    const calls = { count: 0 };
    mswServer.use(
      sequencedCreateHandler([sameDate(false)], calls),
      http.get(COLLECTION, () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    const { onDone } = renderCapture();

    await fillQuickAndReview(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Ya existe una medición de esta fecha")).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("409 same_values:true en el primer intento (no es reintento) → diálogo, no éxito", async () => {
    const calls = { count: 0 };
    mswServer.use(
      sequencedCreateHandler([sameDate(true)], calls),
      http.get(COLLECTION, () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    const { onDone } = renderCapture();

    await fillQuickAndReview(user);
    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });
});
