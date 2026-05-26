/**
 * Tests para EditConditionsDialog (F-COND F4 — Sheet de edición).
 *
 * Cubre:
 *  - Precarga: los valores actuales aparecen en los inputs al abrir el sheet.
 *  - Submit con cambio: dispara PATCH (via API mock) con el body normalizado
 *    (strings vacíos → null), cierra el sheet y muestra toast de éxito.
 *  - Validación: temperature_c fuera de rango (51) muestra error inline y
 *    NO dispara la mutation.
 *  - a11y: 0 violaciones jest-axe.
 *
 * Estrategia:
 *  - Mockeamos `@/api/raceEvents` para interceptar el PATCH y evitar red.
 *  - El hook `useUpdateRaceEventConditions` necesita un QueryClient real para
 *    invalidar queries — montamos uno por test.
 *  - Usamos fake timers para el setTimeout(1200) del onSuccess (que cierra el
 *    sheet) — patrón determinista, sin esperas reales.
 *  - El Sheet de Radix monta portales; usamos `screen.getByRole` global que
 *    los descubre via document.body, no via el container del render.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceEvents", () => ({
  updateRaceEventConditions: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as raceEventsApi from "@/api/raceEvents";
import { EditConditionsDialog } from "@/components/race/EditConditionsDialog";
import type { RaceEventConditions } from "@/types/raceEvents.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(QueryClientProvider, { client: qc }, ui),
  );
}

const CURRENT_CONDITIONS: Partial<RaceEventConditions> = {
  climate: "Soleado",
  temperature_c: "22",
  surface_condition: "seca",
  altitude_msnm: 1000,
  weather_notes: "Pista limpia.",
};

const RESPONSE_OK: RaceEventConditions = {
  race_event_id: 42,
  climate: "Lluvioso",
  temperature_c: "18.5",
  surface_condition: "barro",
  altitude_msnm: 1340,
  weather_notes: "Lluvia intermitente desde media carrera.",
  updated_at: "2026-05-26T12:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  // Defensa: si algún test deja fake timers activos contamina el siguiente.
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// Test #11 — Precarga
// ---------------------------------------------------------------------------

describe("EditConditionsDialog — precarga de valores", () => {
  it("abre el sheet con los valores actuales reflejados en los inputs", async () => {
    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={CURRENT_CONDITIONS}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    // Esperamos a que el portal del Sheet monte los inputs.
    const tempInput = await screen.findByLabelText(/Temperatura/i);
    expect(tempInput).toHaveValue(22);

    const altInput = screen.getByLabelText(/Altitud/i);
    expect(altInput).toHaveValue(1000);

    const climateInput = screen.getByLabelText(/^Clima$/i);
    expect(climateInput).toHaveValue("Soleado");

    const notesInput = screen.getByLabelText(/Notas adicionales/i);
    expect(notesInput).toHaveValue("Pista limpia.");

    // Surface "seca" → el chip correspondiente debe estar marcado.
    const surfaceGroup = screen.getByRole("group", {
      name: /Condición del terreno/i,
    });
    const secaChip = within(surfaceGroup).getByRole("radio", {
      name: /Seca/i,
    });
    expect(secaChip).toHaveAttribute("data-state", "on");
  });

  it("acepta currentConditions vacío y precarga todo vacío sin romper", async () => {
    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={{}}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    const tempInput = await screen.findByLabelText(/Temperatura/i);
    // type="number" con value="" se reporta como null por testing-library.
    expect(tempInput).toHaveValue(null);
    expect(screen.getByLabelText(/Altitud/i)).toHaveValue(null);
    expect(screen.getByLabelText(/^Clima$/i)).toHaveValue("");
    expect(screen.getByLabelText(/Notas adicionales/i)).toHaveValue("");
  });
});

// ---------------------------------------------------------------------------
// Test #12 — Submit dispara PATCH
// ---------------------------------------------------------------------------

describe("EditConditionsDialog — submit", () => {
  it("PATCH con body normalizado + toast éxito + cierra sheet tras delay", async () => {
    // Nota: el dialog usa setTimeout(1200) para cerrar el sheet tras éxito.
    // Mezclar fake timers + TanStack Query + RHF + userEvent lleva a races
    // (el resolver de la promesa queda atrapado entre microtasks y timers
    // simulados). Usamos timers reales y `waitFor` con timeout ampliado —
    // sigue siendo determinista porque el setTimeout es de 1.2 s.
    vi.mocked(raceEventsApi.updateRaceEventConditions).mockResolvedValue(
      RESPONSE_OK,
    );

    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={CURRENT_CONDITIONS}
        open={true}
        onOpenChange={onOpenChange}
      />,
    );

    // Modificamos solo la temperatura para validar que el PATCH lleva el
    // nuevo valor. El resto del body llega con lo que ya estaba precargado.
    const tempInput = await screen.findByLabelText(/Temperatura/i);
    await user.clear(tempInput);
    await user.type(tempInput, "18.5");

    // Click en Guardar (botón type=submit del footer, asociado al form).
    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    // Verifica que se llamó al API con (raceEventId, body).
    await waitFor(() =>
      expect(raceEventsApi.updateRaceEventConditions).toHaveBeenCalledTimes(1),
    );
    const [calledId, calledBody] = vi.mocked(
      raceEventsApi.updateRaceEventConditions,
    ).mock.calls[0];
    expect(calledId).toBe(42);
    // El body normaliza temperature_c al string ingresado por el input number.
    // El resto se preserva del precargado.
    expect(calledBody).toMatchObject({
      climate: "Soleado",
      surface_condition: "seca",
      weather_notes: "Pista limpia.",
    });
    // Temperatura: el form pasa el string "18.5" tal cual al body.
    expect(String(calledBody.temperature_c)).toBe("18.5");
    // Altitud: precargada 1000 → el input devuelve string "1000" y el dialog
    // lo convierte a number via parseFloat.
    expect(calledBody.altitude_msnm).toBe(1000);

    // Toast de éxito visible.
    await waitFor(() =>
      expect(
        screen.getByText(/Condiciones guardadas correctamente/i),
      ).toBeInTheDocument(),
    );

    // El sheet se cierra tras setTimeout(1200). Esperamos al callback con
    // un timeout > 1.2s para cubrir el delay con holgura.
    await waitFor(
      () => expect(onOpenChange).toHaveBeenCalledWith(false),
      { timeout: 2_500 },
    );
  });

  it("strings vacíos en notas/clima se envían como null", async () => {
    vi.mocked(raceEventsApi.updateRaceEventConditions).mockResolvedValue(
      RESPONSE_OK,
    );
    const user = userEvent.setup();

    wrap(
      <EditConditionsDialog
        raceEventId={42}
        // currentConditions vacío → todos los strings inician en ""
        currentConditions={{}}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    // Submit sin tocar nada (todos los campos vacíos).
    const saveBtn = await screen.findByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    await waitFor(() =>
      expect(raceEventsApi.updateRaceEventConditions).toHaveBeenCalledTimes(1),
    );
    const [, body] = vi.mocked(raceEventsApi.updateRaceEventConditions).mock
      .calls[0];
    // Contrato: strings vacíos se normalizan a null antes del PATCH.
    expect(body.climate).toBeNull();
    expect(body.weather_notes).toBeNull();
    expect(body.temperature_c).toBeNull();
    expect(body.altitude_msnm).toBeNull();
    expect(body.surface_condition).toBeNull();
  });

  it("error en mutation muestra toast de error y NO cierra el sheet", async () => {
    vi.mocked(raceEventsApi.updateRaceEventConditions).mockRejectedValue(
      new Error("Boom"),
    );
    const onOpenChange = vi.fn();
    const user = userEvent.setup();

    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={CURRENT_CONDITIONS}
        open={true}
        onOpenChange={onOpenChange}
      />,
    );

    const saveBtn = await screen.findByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    await waitFor(() =>
      expect(
        screen.getByText(/No se pudieron guardar las condiciones/i),
      ).toBeInTheDocument(),
    );
    // El sheet no se cierra en error
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Test #13 — Validación cliente
// ---------------------------------------------------------------------------

describe("EditConditionsDialog — validación", () => {
  it("temperature_c=51 muestra error inline y NO dispara submit", async () => {
    vi.mocked(raceEventsApi.updateRaceEventConditions).mockResolvedValue(
      RESPONSE_OK,
    );
    const user = userEvent.setup();

    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={{}}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    const tempInput = await screen.findByLabelText(/Temperatura/i);
    await user.clear(tempInput);
    await user.type(tempInput, "51");

    const saveBtn = screen.getByRole("button", { name: /^Guardar$/i });
    await user.click(saveBtn);

    // Mensaje de error con role="alert" — sin esperar timers, RHF lo emite sync.
    const alert = await screen.findByText(/Debe estar entre 0 y 50 °C/i);
    expect(alert).toBeInTheDocument();
    // aria-invalid debería estar marcado en el input.
    expect(tempInput).toHaveAttribute("aria-invalid", "true");

    // La mutation NO se dispara porque el schema invalida.
    expect(raceEventsApi.updateRaceEventConditions).not.toHaveBeenCalled();
  });

  it("altitude_msnm=6000 también bloquea el submit (cota superior)", async () => {
    vi.mocked(raceEventsApi.updateRaceEventConditions).mockResolvedValue(
      RESPONSE_OK,
    );
    const user = userEvent.setup();

    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={{}}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    const altInput = await screen.findByLabelText(/Altitud/i);
    await user.type(altInput, "6000");

    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    expect(
      await screen.findByText(/Debe estar entre 0 y 5000 msnm/i),
    ).toBeInTheDocument();
    expect(raceEventsApi.updateRaceEventConditions).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Test #16 — A11y
// ---------------------------------------------------------------------------

describe("EditConditionsDialog — accesibilidad", () => {
  it("sheet abierto: 0 violaciones serias/críticas", async () => {
    // Pasamos el `document.body` a axe porque el Sheet de Radix monta el
    // contenido en un portal fuera del container del render. Asi axe analiza
    // el árbol completo, incluyendo el form en el portal.
    wrap(
      <EditConditionsDialog
        raceEventId={42}
        currentConditions={CURRENT_CONDITIONS}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );
    // Esperamos a que el portal monte.
    await screen.findByLabelText(/Temperatura/i);
    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
