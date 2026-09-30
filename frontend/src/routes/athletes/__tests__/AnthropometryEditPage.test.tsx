import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import {
  capturingPlausibilityHandler,
  forbiddenModifyHandler,
  makeAnthropometricRecord,
  sameDateConflictHandler,
  skinfoldConflictHandler,
} from "@/test/msw/anthropometryHandlers";
import type {
  AnthropometryUpdate,
  PlausibilityCheckRequest,
} from "@/types/anthropometry.types";
import { Sex } from "@/types/enums";

import { AnthropometryEditPage } from "../AnthropometryEditPage";

// Fixtures ficticias: sin nombres ni datos reales de menores.
const ATHLETE_ID = 17;
const RECORD_ID = 812;
const RECORD_PATH = "*/api/athletes/:athleteId/anthropometry/:recordId";

const ATHLETE = {
  id: ATHLETE_ID,
  user_id: 1,
  first_name: "Deportista",
  last_name: "Prueba",
  birth_date: "2014-03-01",
  sex: Sex.M,
  club_join_date: null,
  years_in_club: null,
  age_decimal: 12.5,
  category: "Infantil",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function baseHandlers(canModify = true) {
  return [
    http.get("*/api/athletes/:athleteId", () => HttpResponse.json(ATHLETE)),
    http.get("*/api/athletes/:athleteId/anthropometry", () =>
      HttpResponse.json([
        makeAnthropometricRecord({
          id: RECORD_ID,
          athlete_id: ATHLETE_ID,
          evaluation_date: "2026-09-20",
          weight_kg: 45.5,
          standing_height_cm: 150,
          sitting_height_cm: 72,
          arm_span_cm: 151,
          can_modify: canModify,
        }),
      ]),
    ),
  ];
}

function renderEdit() {
  return renderWithProviders(
    <Routes>
      <Route path="/athletes/:id/anthropometry/:recordId/edit" element={<AnthropometryEditPage />} />
      <Route path="/athletes/:id" element={<p>Perfil del deportista</p>} />
    </Routes>,
    { initialEntries: [`/athletes/${ATHLETE_ID}/anthropometry/${RECORD_ID}/edit`] },
  );
}

async function reviewAndSave(user: UserEvent) {
  await user.click(await screen.findByRole("button", { name: "Revisar y guardar" }));
  await screen.findByRole("heading", { name: "Revisar" });
  await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
}

describe("AnthropometryEditPage (T024/T026)", () => {
  let plausibilitySink: PlausibilityCheckRequest[];

  beforeEach(() => {
    window.localStorage.clear();
    plausibilitySink = [];
    mswServer.use(...baseHandlers(), capturingPlausibilityHandler(plausibilitySink));
  });

  it("precarga la medición con la talla neta y el banco en 0; axe", async () => {
    const { container } = renderEdit();
    const form = await screen.findByRole("form", { name: "Captura rápida de medición" });
    expect(within(form).getByLabelText("Fecha de la medición")).toHaveValue("2026-09-20");
    expect(within(form).getByLabelText("Peso (kg)")).toHaveValue("45,5");
    expect(within(form).getByLabelText("Talla de pie (cm)")).toHaveValue("150");
    expect(within(form).getByLabelText(/Lectura del tallímetro/)).toHaveValue("72");
    expect(within(form).getByLabelText("Altura del banco (cm)")).toHaveValue("0");
    expect(within(form).getByLabelText(/Envergadura/)).toHaveValue("151");
    expect(
      screen.getByText(
        "Al guardar se recalculan el estado de maduración, los percentiles y la explicación de IA de esta medición.",
      ),
    ).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("guarda con PUT (plausibilidad con record_id) y vuelve al perfil", async () => {
    const puts: AnthropometryUpdate[] = [];
    mswServer.use(
      http.put(RECORD_PATH, async ({ request }) => {
        const body = (await request.json()) as AnthropometryUpdate;
        puts.push(body);
        return HttpResponse.json(makeAnthropometricRecord({ ...body, id: RECORD_ID }));
      }),
    );
    const user = userEvent.setup();
    const { container } = renderEdit();

    const weight = await screen.findByLabelText("Peso (kg)");
    await user.clear(weight);
    await user.type(weight, "46");
    await user.click(screen.getByRole("button", { name: "Revisar y guardar" }));
    await screen.findByRole("heading", { name: "Revisar" });
    await waitFor(() => expect(plausibilitySink).toHaveLength(1));
    expect(plausibilitySink[0]).toMatchObject({ record_id: RECORD_ID, weight_kg: 46 });
    await waitFor(() => expect(screen.queryByText("Revisando las medidas…")).not.toBeInTheDocument());
    expect(await axe(container)).toHaveNoViolations();
    // En edición no se ofrece la salida de pliegues.
    expect(screen.queryByRole("button", { name: /agregar pliegues/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("Perfil del deportista")).toBeInTheDocument();
    expect(puts).toHaveLength(1);
    expect(puts[0]).toMatchObject({
      evaluation_date: "2026-09-20",
      weight_kg: 46,
      standing_height_cm: 150,
      sitting_height_cm: 72,
      arm_span_cm: 151,
    });
  });

  it("403 → copia de autoría, sin «Reintentar»", async () => {
    mswServer.use(forbiddenModifyHandler("put"));
    const user = userEvent.setup();
    renderEdit();

    await reviewAndSave(user);
    expect(
      await screen.findByText("Solo quien tomó esta medición o un administrador puede modificarla."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("sin can_modify muestra la copia de autoría y no el formulario", async () => {
    mswServer.use(...baseHandlers(false));
    renderEdit();
    expect(
      await screen.findByText(/Solo quien tomó esta medición o un administrador puede modificarla\./),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Captura rápida de medición" })).not.toBeInTheDocument();
  });

  it("409 misma fecha → copia de fecha repetida", async () => {
    mswServer.use(sameDateConflictHandler("put", { existingRecordId: 811 }));
    const user = userEvent.setup();
    renderEdit();

    await reviewAndSave(user);
    expect(await screen.findByText(/Ya existe una medición de esta fecha/)).toBeInTheDocument();
  });

  it("409 intervalo de pliegues → misma copia del asistente 046", async () => {
    mswServer.use(skinfoldConflictHandler("skinfold_interval_too_short", "2026-10-20"));
    const user = userEvent.setup();
    renderEdit();

    await reviewAndSave(user);
    expect(
      await screen.findByText(
        /Entre dos mediciones debe pasar un intervalo mínimo para que el cambio sea confiable: la siguiente puede tomarse desde el/,
      ),
    ).toBeInTheDocument();
  });

  it("409 edad mínima de pliegues → copia del 046", async () => {
    mswServer.use(skinfoldConflictHandler("athlete_too_young"));
    const user = userEvent.setup();
    renderEdit();

    await reviewAndSave(user);
    expect(
      await screen.findByText(/Los pliegues cutáneos se miden desde los 9 años\./),
    ).toBeInTheDocument();
  });

  it("error de red → banner sin conexión con «Reintentar»", async () => {
    mswServer.use(http.put(RECORD_PATH, () => HttpResponse.error()));
    const user = userEvent.setup();
    renderEdit();

    await reviewAndSave(user);
    expect(
      await screen.findByText("Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});
