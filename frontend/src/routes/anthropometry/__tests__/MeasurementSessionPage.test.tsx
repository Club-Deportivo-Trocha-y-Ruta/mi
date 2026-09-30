/**
 * MeasurementSessionPage (feature 048, US3, T047): selección, cola y resumen
 * de la jornada de medición grupal.
 *
 * La captura individual (`AnthropometryCapture`) se sustituye por un doble
 * mínimo: su flujo, su 409 y su axe ya se prueban en
 * `AnthropometryCapture.test.tsx`. Aquí interesa la orquestación de la cola.
 * Fixtures ficticias: nombres inventados, sin datos de menores reales.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router-dom";

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { useMeasurementSessionStore } from "@/store/measurementSession.store";
import type { RosterRow } from "@/types/anthropometry.types";
import type { AnthropometryCaptureProps } from "@/components/athletes/anthropometry-capture/AnthropometryCapture";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

vi.mock("@/components/athletes/anthropometry-capture/AnthropometryCapture", () => ({
  AnthropometryCapture: (props: AnthropometryCaptureProps) => (
    <div data-testid="capture-double">
      <p>
        Captura {props.athlete.id} · fecha {props.lockedDate}
      </p>
      <button
        type="button"
        onClick={() =>
          props.onDone({
            recordId: 1000 + props.athlete.id,
            intent: "finish",
            record: {
              plausibility_flags: props.athlete.id === 2 ? ["weight_change_large"] : [],
            } as never,
          })
        }
      >
        Simular guardado
      </button>
      {props.allowSkinfoldsExit !== false && (
        <button
          type="button"
          onClick={() => props.onDone({ recordId: 2000 + props.athlete.id, intent: "skinfolds" })}
        >
          Simular pliegues
        </button>
      )}
    </div>
  ),
}));

import { toast } from "sonner";
import { MeasurementSessionPage } from "@/routes/anthropometry/MeasurementSessionPage";

function row(overrides: Partial<RosterRow>): RosterRow {
  return {
    athlete_id: 1,
    full_name: "Deportista Uno",
    category: "Infantil A",
    sex: "M",
    birth_date: "2014-03-01",
    last_evaluation_date: "2026-06-10",
    has_record_on_date: false,
    skinfolds_eligible: true,
    ...overrides,
  };
}

const ROSTER: RosterRow[] = [
  row({ athlete_id: 1, full_name: "Deportista Uno", category: "Infantil A" }),
  row({
    athlete_id: 2,
    full_name: "Deportista Dos",
    category: "Infantil A",
    skinfolds_eligible: false,
  }),
  row({
    athlete_id: 3,
    full_name: "Deportista Tres",
    category: "Pre-juvenil B",
    last_evaluation_date: null,
  }),
  row({
    athlete_id: 4,
    full_name: "Deportista Cuatro",
    category: "Pre-juvenil B",
    has_record_on_date: true,
  }),
];

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function renderPage() {
  mswServer.use(http.get("*/api/anthropometry/roster", () => HttpResponse.json(ROSTER)));
  return renderWithProviders(
    <Routes>
      <Route path="/anthropometry/session" element={<MeasurementSessionPage />} />
      <Route path="*" element={<LocationProbe />} />
    </Routes>,
    { initialEntries: ["/anthropometry/session"] },
  );
}

async function startWith(user: ReturnType<typeof userEvent.setup>, names: string[]) {
  await screen.findByText("Deportista Uno");
  for (const name of names) {
    await user.click(screen.getByRole("checkbox", { name }));
  }
  await user.click(screen.getByRole("button", { name: `Empezar jornada (${names.length})` }));
}

beforeEach(() => {
  useMeasurementSessionStore.getState().reset();
});

afterEach(() => {
  useMeasurementSessionStore.getState().reset();
  vi.clearAllMocks();
});

describe("MeasurementSessionPage — selección", () => {
  it("sin jornada abre la selección, con «Medido hoy» y la última medición; axe", async () => {
    const { container } = renderPage();
    expect(await screen.findByText("Deportista Uno")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Jornada de medición" })).toBeInTheDocument();

    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(4);
    const cuatro = cards.find((c) => within(c).queryByText("Deportista Cuatro"))!;
    expect(within(cuatro).getByText("Medido hoy")).toBeInTheDocument();
    const uno = cards.find((c) => within(c).queryByText("Deportista Uno"))!;
    expect(within(uno).queryByText("Medido hoy")).not.toBeInTheDocument();
    expect(within(uno).getByText(/Última medición: 10\/06\/2026/)).toBeInTheDocument();
    const tres = cards.find((c) => within(c).queryByText("Deportista Tres"))!;
    expect(within(tres).getByText(/Sin mediciones/)).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Empezar jornada (0)" })).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("filtra por categoría y «Seleccionar todos los visibles» no suma a los ya medidos", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Deportista Uno");

    await user.click(screen.getByRole("radio", { name: "Pre-juvenil B" }));
    expect(screen.queryByText("Deportista Uno")).not.toBeInTheDocument();
    expect(screen.getByText("Deportista Tres")).toBeInTheDocument();
    expect(screen.getByText("Deportista Cuatro")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Seleccionar todos los visibles" }));
    expect(screen.getByRole("checkbox", { name: "Deportista Tres" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Deportista Cuatro" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Empezar jornada (1)" })).toBeEnabled();

    // La selección sobrevive al cambio de filtro.
    await user.click(screen.getByRole("radio", { name: "Todas" }));
    await user.click(screen.getByRole("checkbox", { name: "Deportista Uno" }));
    expect(screen.getByRole("button", { name: "Empezar jornada (2)" })).toBeEnabled();
  });

  it("marcar y desmarcar una tarjeta cambia el conteo", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Deportista Uno");
    const cb = screen.getByRole("checkbox", { name: "Deportista Dos" });
    await user.click(cb);
    expect(screen.getByRole("button", { name: "Empezar jornada (1)" })).toBeInTheDocument();
    await user.click(cb);
    expect(screen.getByRole("button", { name: "Empezar jornada (0)" })).toBeDisabled();
  });
});

describe("MeasurementSessionPage — cola", () => {
  it("medir → «Guardado» → siguiente pendiente, con la fecha bloqueada; axe", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    await startWith(user, ["Deportista Uno", "Deportista Dos", "Deportista Tres"]);

    expect(await screen.findByRole("heading", { name: "Deportista Uno" })).toBeInTheDocument();
    expect(screen.getByText("1 de 3")).toBeInTheDocument();
    const date = useMeasurementSessionStore.getState().date!;
    expect(screen.getByText(`Captura 1 · fecha ${date}`)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Simular guardado" }));
    expect(toast.success).toHaveBeenCalledWith("Guardado");
    expect(await screen.findByRole("heading", { name: "Deportista Dos" })).toBeInTheDocument();
    expect(screen.getByText("2 de 3")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Avance de la jornada" })).toHaveAttribute(
      "aria-valuenow",
      "1",
    );
    // El recién guardado es elegible: se ofrece «Agregar pliegues» con returnTo.
    expect(screen.getByRole("link", { name: "Agregar pliegues" })).toHaveAttribute(
      "href",
      "/athletes/1/anthropometry/1001/skinfolds?returnTo=/anthropometry/session",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no ofrece pliegues a quien no es elegible", async () => {
    const user = userEvent.setup();
    renderPage();
    await startWith(user, ["Deportista Dos", "Deportista Tres"]);
    await screen.findByRole("heading", { name: "Deportista Dos" });
    expect(screen.queryByRole("button", { name: "Simular pliegues" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Simular guardado" }));
    await screen.findByRole("heading", { name: "Deportista Tres" });
    expect(screen.queryByRole("link", { name: "Agregar pliegues" })).not.toBeInTheDocument();
  });

  it("«Guardar y agregar pliegues» abre el asistente del 046 con returnTo a la jornada", async () => {
    const user = userEvent.setup();
    renderPage();
    await startWith(user, ["Deportista Uno", "Deportista Tres"]);
    await screen.findByRole("heading", { name: "Deportista Uno" });
    await user.click(screen.getByRole("button", { name: "Simular pliegues" }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/athletes/1/anthropometry/2001/skinfolds?returnTo=/anthropometry/session",
    );
    expect(useMeasurementSessionStore.getState().statusById[1]).toBe("measured");
    expect(useMeasurementSessionStore.getState().currentId).toBe(3);
  });

  it("«Ver lista» permite saltar a un pendiente", async () => {
    const user = userEvent.setup();
    renderPage();
    await startWith(user, ["Deportista Uno", "Deportista Dos", "Deportista Tres"]);
    await screen.findByRole("heading", { name: "Deportista Uno" });

    await user.click(screen.getByRole("button", { name: "Ver lista" }));
    const sheet = await screen.findByRole("dialog", { name: "Lista de la jornada" });
    expect(await axe(sheet)).toHaveNoViolations();
    await user.click(within(sheet).getByRole("button", { name: "Deportista Tres" }));

    expect(await screen.findByRole("heading", { name: "Deportista Tres" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("MeasurementSessionPage — resumen", () => {
  it("omitir → resumen con Medidos («Revisar»), Omitidos y reabrir con «Medir ahora»; axe", async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    await startWith(user, ["Deportista Uno", "Deportista Dos"]);

    await screen.findByRole("heading", { name: "Deportista Uno" });
    await user.click(screen.getByRole("button", { name: "Omitir por hoy" }));
    await screen.findByRole("heading", { name: "Deportista Dos" });
    await user.click(screen.getByRole("button", { name: "Simular guardado" }));

    expect(await screen.findByRole("heading", { name: "Resumen de la jornada" })).toBeInTheDocument();
    const measured = screen.getByRole("region", { name: "Medidos (1)" });
    expect(within(measured).getByRole("link", { name: "Deportista Dos" })).toHaveAttribute(
      "href",
      "/athletes/2/anthropometry/1002/edit",
    );
    expect(within(measured).getByText("Revisar")).toBeInTheDocument();
    const skipped = screen.getByRole("region", { name: "Omitidos (1)" });
    expect(within(skipped).getByText("Deportista Uno")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Pendientes (0)" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();

    await user.click(within(skipped).getByRole("button", { name: "Medir ahora a Deportista Uno" }));
    expect(await screen.findByRole("heading", { name: "Deportista Uno" })).toBeInTheDocument();
    expect(useMeasurementSessionStore.getState().statusById[1]).toBe("pending");
  });

  it("«Ver resumen» muestra pendientes y «Terminar jornada» vuelve a la selección", async () => {
    const user = userEvent.setup();
    renderPage();
    await startWith(user, ["Deportista Uno", "Deportista Tres"]);
    await screen.findByRole("heading", { name: "Deportista Uno" });

    await user.click(screen.getByRole("button", { name: "Ver resumen" }));
    const pending = await screen.findByRole("region", { name: "Pendientes (2)" });
    expect(within(pending).getByText("Deportista Tres")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Terminar jornada" }));
    expect(
      await screen.findByRole("button", { name: /Empezar jornada/ }),
    ).toBeInTheDocument();
    await waitFor(() => expect(useMeasurementSessionStore.getState().date).toBeNull());
  });
});
