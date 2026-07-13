/**
 * Tests para StrengthBlockPicker (feature 032, US1, T010) — biblioteca de
 * bloques de fuerza del club con adjunto directo a una sesión:
 *   - Los bloques existentes del club se listan como tarjetas con botón
 *     "Adjuntar a la sesión".
 *   - Adjuntar con éxito actualiza la tarjeta a un estado de confirmación.
 *   - Un `409` (ya adjunto) se muestra como un aviso suave, no como un error
 *     bloqueante (`role="alert"` nunca aparece para ese caso).
 *   - `AgeBandGuardrailDialog` nunca se invoca desde este flujo — el adjunto
 *     no tiene lógica de edad (research.md R9); esto protege contra una
 *     regresión futura que la introduzca por error.
 *   - jest-axe sin violaciones.
 *
 * Estrategia: MSW real vía mswServer.use(strengthHandlers-derivados). No se
 * mockea useAuthStore — `useStrengthBlocks`/`useAttachBlock` no dependen del
 * store de autenticación (a diferencia de `useTrainingSessions`).
 */
import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { http, HttpResponse } from "msw";

import { StrengthBlockPicker } from "@/components/training/session-plan/StrengthBlockPicker";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  strengthHandlers,
  strengthAttachAlreadyAttachedHandler,
  strengthAttachErrorHandler,
  makeBlockList,
  makeBlockOut,
} from "@/test/msw/strengthHandlers";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — dos bloques distinguibles por nombre
// ---------------------------------------------------------------------------

const BLOCK_A = makeBlockOut({
  id: 1,
  name: "Bloque ficticio — tren inferior",
  target_age_band: "10-12",
});

const BLOCK_B = makeBlockOut({
  id: 2,
  name: "Bloque ficticio — tren superior",
  target_age_band: "13-15",
});

const twoBlocksHandler = http.get("*/api/strength/blocks", () =>
  HttpResponse.json(makeBlockList([BLOCK_A, BLOCK_B])),
);

function renderPicker(trainingSessionId = 5) {
  return renderWithProviders(
    <StrengthBlockPicker trainingSessionId={trainingSessionId} />,
  );
}

beforeEach(() => {
  // `twoBlocksHandler` va primero: dentro de un mismo `.use(...)`, MSW
  // resuelve por orden de aparición y el handler por defecto de
  // `strengthHandlers` para `GET /api/strength/blocks` (un solo bloque)
  // matchearía antes si fuera al revés.
  mswServer.use(twoBlocksHandler, ...strengthHandlers);
});

// ---------------------------------------------------------------------------
// Suite: lista de bloques existentes
// ---------------------------------------------------------------------------

describe("StrengthBlockPicker — lista de bloques del club", () => {
  it("renderiza los bloques existentes como una lista para adjuntar", async () => {
    renderPicker();

    expect(
      await screen.findByText("Bloque ficticio — tren inferior"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Bloque ficticio — tren superior"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Adjuntar a la sesión" }),
    ).toHaveLength(2);
  });

  it("muestra un estado vacío cuando el club no tiene bloques guardados", async () => {
    mswServer.use(
      http.get("*/api/strength/blocks", () =>
        HttpResponse.json(makeBlockList([])),
      ),
    );
    renderPicker();

    expect(
      await screen.findByText(
        "Aún no hay bloques de fuerza guardados en el club",
      ),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: adjuntar con éxito
// ---------------------------------------------------------------------------

describe("StrengthBlockPicker — adjuntar con éxito", () => {
  it("adjunta un bloque y actualiza la tarjeta a confirmado", async () => {
    const user = userEvent.setup();
    renderPicker();

    await screen.findByText("Bloque ficticio — tren inferior");
    const buttons = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(buttons[0]);

    await waitFor(() => {
      expect(
        screen.getAllByText("Adjuntado a la sesión").length,
      ).toBeGreaterThan(0);
    });

    // El otro bloque sigue disponible para adjuntar, sin verse afectado.
    expect(
      screen.getAllByRole("button", { name: "Adjuntar a la sesión" }),
    ).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Suite: 409 — ya adjunto (aviso suave, no error bloqueante)
// ---------------------------------------------------------------------------

describe("StrengthBlockPicker — 409 ya adjunto", () => {
  it("renderiza un aviso suave, no un error bloqueante", async () => {
    mswServer.use(strengthAttachAlreadyAttachedHandler);

    const user = userEvent.setup();
    renderPicker();

    await screen.findByText("Bloque ficticio — tren inferior");
    const [firstButton] = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(firstButton);

    expect(
      await screen.findByText("Ya está adjunto a esta sesión"),
    ).toBeInTheDocument();
    // No debe existir ninguna alerta bloqueante producto del 409.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: error real (500) — sí se muestra como alerta bloqueante
// ---------------------------------------------------------------------------

describe("StrengthBlockPicker — error inesperado", () => {
  it("muestra una alerta inline y conserva el botón para reintentar", async () => {
    mswServer.use(strengthAttachErrorHandler);

    const user = userEvent.setup();
    renderPicker();

    await screen.findByText("Bloque ficticio — tren inferior");
    const [firstButton] = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(firstButton);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Adjuntar a la sesión" }),
    ).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Suite: regresión — sin compuerta por edad en el adjunto
// ---------------------------------------------------------------------------

describe("StrengthBlockPicker — sin compuerta por edad (research.md R9)", () => {
  it("no invoca AgeBandGuardrailDialog en un adjunto exitoso", async () => {
    const user = userEvent.setup();
    renderPicker();

    await screen.findByText("Bloque ficticio — tren inferior");
    const [firstButton] = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(firstButton);

    await waitFor(() => {
      expect(
        screen.getAllByText("Adjuntado a la sesión").length,
      ).toBeGreaterThan(0);
    });

    expect(
      screen.queryByText("Ejercicio fuera de la franja de edad"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("no invoca AgeBandGuardrailDialog en un 409 ya-adjunto", async () => {
    mswServer.use(strengthAttachAlreadyAttachedHandler);

    const user = userEvent.setup();
    renderPicker();

    await screen.findByText("Bloque ficticio — tren inferior");
    const [firstButton] = screen.getAllByRole("button", {
      name: "Adjuntar a la sesión",
    });
    await user.click(firstButton);

    await screen.findByText("Ya está adjunto a esta sesión");

    expect(
      screen.queryByText("Ejercicio fuera de la franja de edad"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("StrengthBlockPicker — accesibilidad", () => {
  it("no tiene violaciones de a11y con la lista de bloques visible", async () => {
    const { container } = renderPicker();

    await screen.findByText("Bloque ficticio — tren inferior");

    expect(await axe(container)).toHaveNoViolations();
  });
});
