/**
 * Tests — SkinfoldWizard (feature 046, US1, T019/T028).
 *
 * Escrito antes de T028 (TDD, tasks.md): falla hasta que
 * `SkinfoldWizard.tsx` exista con esta forma. Contrato asumido (documentado
 * aquí para quien implemente T028): props `{ athleteId, recordId, ageYears,
 * onDone }`; usa `saveSkinfolds` de `@/api/bodyComposition` para el envío
 * final (mock de red, no del hook, para no acoplar el test a la forma
 * exacta de `useSaveSkinfolds`); borrador con `useFormDraft` bajo la clave
 * `skinfolds:{recordId}` — probado contra `localStorage` real, no mockeado.
 *
 * Cubre (tasks.md T019):
 *  - el pre-check nunca bloquea el avance;
 *  - "Hoy prefiere no medirse" en el pre-check arma UN solo payload con los
 *    seis sitios `{declined: true}` sin pasar por los pasos de sitio, sin
 *    pedir motivo;
 *  - el foco se mueve al encabezado de cada paso;
 *  - el banner de restaurar borrador aparece tras un remount con datos
 *    guardados;
 *  - la revisión final muestra "Omitido" para un sitio declinado;
 *  - el envío llama a `saveSkinfolds` con el payload del contrato;
 *  - un error de red muestra el mensaje offline.
 *
 * Datos: sintéticos, sin nombre de ningún deportista real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock parcial: el pre-check también monta `FieldGuideDownloadButton`
// (US5), que referencia `downloadFieldGuide` del mismo módulo.
vi.mock("@/api/bodyComposition", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/bodyComposition")>()),
  saveSkinfolds: vi.fn(),
  downloadFieldGuide: vi.fn(),
}));

import { saveSkinfolds } from "@/api/bodyComposition";
import { SkinfoldWizard } from "@/components/athletes/body-composition/SkinfoldWizard";

const ATHLETE_ID = 17;
const RECORD_ID = 812;
const DRAFT_STORAGE_KEY_FRAGMENT = `skinfolds:${RECORD_ID}`;

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function renderWizard(onDone = vi.fn()) {
  return wrap(
    <SkinfoldWizard athleteId={ATHLETE_ID} recordId={RECORD_ID} ageYears={12} onDone={onDone} />,
  );
}

async function fillTwoReadings(user: ReturnType<typeof userEvent.setup>, r1: string, r2: string) {
  await user.type(screen.getByLabelText("Primera lectura (mm)"), r1);
  await user.type(screen.getByLabelText("Segunda lectura (mm)"), r2);
  await user.click(screen.getByRole("button", { name: "Siguiente" }));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(saveSkinfolds).mockReset();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("SkinfoldWizard", () => {
  it("el pre-check nunca bloquea: 'Siguiente' está habilitado sin marcar nada", () => {
    renderWizard();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeEnabled();
  });

  it("'Hoy prefiere no medirse' envía un solo payload con los seis sitios declinados, sin pasar por los pasos de sitio", async () => {
    const user = userEvent.setup();
    vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
    renderWizard();

    await user.click(screen.getByRole("button", { name: "Hoy prefiere no medirse" }));

    await waitFor(() => expect(saveSkinfolds).toHaveBeenCalledTimes(1));
    const [athleteIdArg, recordIdArg, payload] = vi.mocked(saveSkinfolds).mock.calls[0];
    expect(athleteIdArg).toBe(ATHLETE_ID);
    expect(recordIdArg).toBe(RECORD_ID);
    expect(Object.keys(payload.sites)).toHaveLength(6);
    for (const site of Object.values(payload.sites)) {
      expect(site).toEqual({ declined: true });
    }
    // Nunca se visitaron los pasos de sitio: no aparece ningún input numérico.
    expect(screen.queryByLabelText("Primera lectura (mm)")).not.toBeInTheDocument();
  });

  it("no pide un motivo al declinar todo el set", async () => {
    const user = userEvent.setup();
    vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
    renderWizard();
    await user.click(screen.getByRole("button", { name: "Hoy prefiere no medirse" }));
    expect(screen.queryByRole("textbox", { name: /motivo/i })).not.toBeInTheDocument();
  });

  it("mueve el foco al encabezado del paso al avanzar", async () => {
    const user = userEvent.setup();
    renderWizard();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    const heading = screen.getByRole("heading", { level: 2 });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("muestra el banner de restaurar borrador tras un remount con datos guardados", async () => {
    const user = userEvent.setup();
    const { unmount } = renderWizard();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await fillTwoReadings(user, "8.0", "9.0");

    await waitFor(() => {
      const stored = Object.keys(window.localStorage).some((key) =>
        key.includes(DRAFT_STORAGE_KEY_FRAGMENT),
      );
      expect(stored).toBe(true);
    });

    unmount();
    renderWizard();

    expect(
      screen.getByText(/tienes un borrador sin guardar|continuar donde quedaste/i),
    ).toBeInTheDocument();
  });

  it("la revisión final muestra 'Omitido' para un sitio marcado como declinado", async () => {
    const user = userEvent.setup();
    renderWizard();

    // Precheck → sitio 1 (tríceps): lo omite.
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await user.click(screen.getByRole("button", { name: "Omitir este sitio" }));

    // Avanza el resto de sitios con dos lecturas válidas hasta la revisión.
    for (let i = 0; i < 4; i += 1) {
      await fillTwoReadings(user, "8.0", "8.5");
    }
    await fillTwoReadings(user, "8.0", "8.5");

    const review = await screen.findByRole("heading", { name: "Revisar medición" });
    const table = review.closest("div")?.parentElement ?? document.body;
    expect(within(table as HTMLElement).getByText("Omitido")).toBeInTheDocument();
  });

  it("al enviar, llama a saveSkinfolds con el payload del contrato", async () => {
    const user = userEvent.setup();
    vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
    renderWizard();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    for (let i = 0; i < 6; i += 1) {
      await fillTwoReadings(user, "8.0", "8.5");
    }

    await user.click(screen.getByRole("button", { name: "Guardar medición" }));

    await waitFor(() => expect(saveSkinfolds).toHaveBeenCalledTimes(1));
    const [, , payload] = vi.mocked(saveSkinfolds).mock.calls[0];
    expect(payload).toHaveProperty("caliper_model");
    expect(Object.keys(payload.sites)).toHaveLength(6);
  });

  it("muestra el mensaje offline cuando saveSkinfolds falla por red", async () => {
    const user = userEvent.setup();
    vi.mocked(saveSkinfolds).mockRejectedValue(new Error("Network Error"));
    renderWizard();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    for (let i = 0; i < 6; i += 1) {
      await fillTwoReadings(user, "8.0", "8.5");
    }
    await user.click(screen.getByRole("button", { name: "Guardar medición" }));

    expect(
      await screen.findByText("Sin conexión: se guardará cuando vuelvas a tener señal"),
    ).toBeInTheDocument();
  });
});
