/**
 * Tests para TechniqueAttachPicker (feature 032, US1, T009):
 *   - Multi-select → adjuntar → éxito actualiza la lista de técnica de la
 *     sesión (Plan section).
 *   - Un adjunto fallido preserva las selecciones del coach y permite
 *     reintentar.
 *   - Un reintento que simula "el servidor ya comprometió el cambio, el
 *     cliente solo vio un error" no duplica la lista renderizada (FR-009).
 *   - Nunca se emite una petición para crear una sesión de entrenamiento
 *     (SC-002) — este componente solo adjunta a una sesión que ya existe.
 *   - jest-axe: cero violaciones.
 *
 * Estrategia de mock: MSW para todo el flujo (catálogo, skills, materiales,
 * GET/POST .../sessions/:id/exercises vía createStatefulSessionExercisesHandlers).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { TechniqueAttachPicker } from "../TechniqueAttachPicker";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import {
  techniqueHandlers,
  createStatefulSessionExercisesHandlers,
} from "@/test/msw/techniqueHandlers";

expect.extend(toHaveNoViolations);

const SESSION_ID = 42;

function renderPicker() {
  return renderWithProviders(<TechniqueAttachPicker sessionId={SESSION_ID} />);
}

// ---------------------------------------------------------------------------
// Selección múltiple en el catálogo
// ---------------------------------------------------------------------------

async function selectExercises(names: string[]) {
  const user = userEvent.setup();
  for (const name of names) {
    const checkbox = screen.getByRole("checkbox", { name });
    await user.click(checkbox);
  }
  return user;
}

// ---------------------------------------------------------------------------
// Suite: éxito — multi-select → adjuntar → lista actualizada
// ---------------------------------------------------------------------------

describe("TechniqueAttachPicker — adjunto exitoso", () => {
  let sessionExercises: ReturnType<typeof createStatefulSessionExercisesHandlers>;

  beforeEach(() => {
    sessionExercises = createStatefulSessionExercisesHandlers(SESSION_ID);
    mswServer.use(...techniqueHandlers, ...sessionExercises.handlers);
  });

  it("selecciona varios ejercicios y los adjunta a la sesión en un solo envío", async () => {
    renderPicker();

    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    const user = await selectExercises(["Slalom con conos", "Gymkhana básica"]);

    const attachButton = screen.getByRole("button", {
      name: /Adjuntar a la sesión \(2\)/,
    });
    await user.click(attachButton);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Ejercicios de técnica en esta sesión" }),
      ).toBeInTheDocument();
    });

    const list = screen.getByRole("list");
    expect(within(list).getByText("Slalom con conos")).toBeInTheDocument();
    expect(within(list).getByText("Gymkhana básica")).toBeInTheDocument();
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);

    // Las selecciones se limpian tras el éxito.
    expect(
      screen.queryByRole("button", { name: /Adjuntar a la sesión \(/ }),
    ).not.toBeInTheDocument();
  });

  it("nunca emite una petición para crear una sesión de entrenamiento (SC-002)", async () => {
    const createSessionSpy = vi.fn();
    const listener = ({ request }: { request: Request }) => {
      if (request.method === "POST" && request.url.includes("/api/training-sessions")) {
        createSessionSpy();
      }
    };
    mswServer.events.on("request:start", listener);

    try {
      renderPicker();
      await waitFor(() => {
        expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
      });

      const user = await selectExercises(["Slalom con conos"]);
      await user.click(
        screen.getByRole("button", { name: /Adjuntar a la sesión \(1\)/ }),
      );

      await waitFor(() => {
        expect(
          screen.getByRole("heading", { name: "Ejercicios de técnica en esta sesión" }),
        ).toBeInTheDocument();
      });

      expect(createSessionSpy).not.toHaveBeenCalled();
    } finally {
      mswServer.events.removeListener("request:start", listener);
    }
  });
});

// ---------------------------------------------------------------------------
// Suite: adjunto fallido — preserva selecciones, permite reintentar
// ---------------------------------------------------------------------------

describe("TechniqueAttachPicker — adjunto fallido y reintento", () => {
  it("preserva las selecciones tras un error y permite reintentar sin duplicar la lista", async () => {
    // Primera llamada POST falla en el cliente, pero el store queda mutado —
    // simula "el servidor ya comprometió, el cliente solo vio un error"
    // (FR-009). La segunda llamada (reintento con el mismo payload) dedupea
    // server-side y responde 201 sin filas nuevas.
    const sessionExercises = createStatefulSessionExercisesHandlers(SESSION_ID, [], {
      failPostCallNumbers: [1],
    });
    mswServer.use(...techniqueHandlers, ...sessionExercises.handlers);

    renderPicker();
    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    const user = await selectExercises(["Slalom con conos"]);
    await user.click(
      screen.getByRole("button", { name: /Adjuntar a la sesión \(1\)/ }),
    );

    // El error se muestra y la selección sigue marcada — el checkbox no se limpia.
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("checkbox", { name: "Slalom con conos" }),
    ).toBeChecked();
    expect(
      screen.getByRole("button", { name: /Adjuntar a la sesión \(1\)/ }),
    ).toBeInTheDocument();

    // Reintento — mismo botón, mismo payload.
    await user.click(
      screen.getByRole("button", { name: /Adjuntar a la sesión \(1\)/ }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Ejercicios de técnica en esta sesión" }),
      ).toBeInTheDocument();
    });

    // No duplicado: una sola fila para "Slalom con conos" en la lista renderizada.
    const list = screen.getByRole("list");
    expect(within(list).getAllByText("Slalom con conos")).toHaveLength(1);
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(sessionExercises.getItems()).toHaveLength(1);

    // El error desaparece tras el reintento exitoso.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("TechniqueAttachPicker — accesibilidad", () => {
  beforeEach(() => {
    const sessionExercises = createStatefulSessionExercisesHandlers(SESSION_ID);
    mswServer.use(...techniqueHandlers, ...sessionExercises.handlers);
  });

  it("no tiene violaciones de accesibilidad con el catálogo cargado", async () => {
    const { container } = renderPicker();

    await waitFor(() => {
      expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
