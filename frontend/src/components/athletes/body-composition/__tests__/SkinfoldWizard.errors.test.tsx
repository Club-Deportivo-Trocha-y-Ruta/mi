/**
 * Tests — SkinfoldWizard, rutas de error y borrador (feature 046, US1, T028).
 *
 * Complementa `SkinfoldWizard.test.tsx` (T019): 409 de intervalo con
 * `next_allowed_date`, borrador conservado tras un error de red, reintento,
 * restaurar/descartar borrador, validación por paso y `onDone`.
 * Datos sintéticos; sin nombres.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";

vi.mock("@/api/bodyComposition", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/bodyComposition")>()),
  saveSkinfolds: vi.fn(),
  downloadFieldGuide: vi.fn(),
}));

import { saveSkinfolds } from "@/api/bodyComposition";
import { SkinfoldWizard } from "@/components/athletes/body-composition/SkinfoldWizard";

const ATHLETE_ID = 17;
const RECORD_ID = 812;

function renderWizard(onDone = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <SkinfoldWizard athleteId={ATHLETE_ID} recordId={RECORD_ID} ageYears={12} onDone={onDone} />
    </QueryClientProvider>,
  );
  return { ...utils, onDone };
}

type User = ReturnType<typeof userEvent.setup>;

async function fillSite(user: User, r1: string, r2: string) {
  await user.type(screen.getByLabelText("Primera lectura (mm)"), r1);
  await user.type(screen.getByLabelText("Segunda lectura (mm)"), r2);
  await user.click(screen.getByRole("button", { name: "Siguiente" }));
}

async function goToReview(user: User) {
  await user.click(screen.getByRole("button", { name: "Siguiente" }));
  for (let i = 0; i < 6; i += 1) {
    await fillSite(user, "8.0", "8.5");
  }
  await screen.findByRole("heading", { name: "Revisar medición" });
}

function draftKeys(): string[] {
  return Object.keys(window.localStorage).filter((k) => k.includes(`skinfolds:${RECORD_ID}`));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(saveSkinfolds).mockReset();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("SkinfoldWizard — errores y borrador", () => {
  it("409 de intervalo: explica la fecha desde la que se puede medir", async () => {
    const user = userEvent.setup();
    vi.mocked(saveSkinfolds).mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            code: "skinfold_interval_too_short",
            message: "interval",
            previous_set_date: "2026-08-01",
            next_allowed_date: "2026-10-30",
          },
        },
      },
    });
    renderWizard();
    await goToReview(user);
    await user.click(screen.getByRole("button", { name: "Guardar medición" }));

    const alert = await screen.findByTestId("skinfold-interval");
    expect(alert).toHaveTextContent("30 de octubre de 2026");
    expect(alert).toHaveTextContent("1 de agosto de 2026");
  });

  it("error de red: conserva el borrador y 'Reintentar' vuelve a enviar", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    vi.mocked(saveSkinfolds)
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({} as never);
    renderWizard(onDone);
    await goToReview(user);
    await waitFor(() => expect(draftKeys()).toHaveLength(1));

    await user.click(screen.getByRole("button", { name: "Guardar medición" }));
    await screen.findByText("Sin conexión: se guardará cuando vuelvas a tener señal");
    expect(draftKeys()).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ declinedAll: false }));
    expect(saveSkinfolds).toHaveBeenCalledTimes(2);
    expect(draftKeys()).toHaveLength(0);
  });

  it("reintenta automáticamente al recuperar la señal", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    vi.mocked(saveSkinfolds)
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({} as never);
    renderWizard(onDone);
    await goToReview(user);
    await user.click(screen.getByRole("button", { name: "Guardar medición" }));
    await screen.findByText("Sin conexión: se guardará cuando vuelvas a tener señal");

    window.dispatchEvent(new Event("online"));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
  });

  it("'Hoy prefiere no medirse' limpia el borrador y avisa declinedAll", async () => {
    const user = userEvent.setup();
    vi.mocked(saveSkinfolds).mockResolvedValue({} as never);
    const { onDone } = renderWizard();
    await user.click(screen.getByRole("button", { name: "Hoy prefiere no medirse" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ declinedAll: true }));
    expect(draftKeys()).toHaveLength(0);
  });

  it("no avanza con una sola lectura y lo explica sin bloquear 'Omitir'", async () => {
    const user = userEvent.setup();
    renderWizard();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await user.type(screen.getByLabelText("Primera lectura (mm)"), "8.0");
    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Revisa las lecturas/);
    expect(screen.getByRole("heading", { name: "Tríceps" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Omitir este sitio" }));
    expect(screen.getByRole("heading", { name: "Bíceps" })).toBeInTheDocument();
  });

  it("restaurar el borrador vuelve al paso y a los valores guardados", async () => {
    const user = userEvent.setup();
    const { unmount } = renderWizard();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await fillSite(user, "8.0", "9.0");
    await waitFor(() => {
      const raw = window.localStorage.getItem(draftKeys()[0] ?? "");
      expect(raw && JSON.parse(raw).step).toBe(2);
    });
    unmount();

    renderWizard();
    await user.click(screen.getByRole("button", { name: "Restaurar" }));
    expect(screen.getByRole("heading", { name: "Bíceps" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Atrás" }));
    expect(screen.getByLabelText("Primera lectura (mm)")).toHaveValue(8);
    expect(screen.getByLabelText("Segunda lectura (mm)")).toHaveValue(9);
  });

  it("descartar el borrador lo borra y oculta el aviso", async () => {
    const user = userEvent.setup();
    const { unmount } = renderWizard();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await fillSite(user, "8.0", "9.0");
    await waitFor(() => expect(draftKeys()).toHaveLength(1));
    unmount();

    renderWizard();
    await user.click(screen.getByRole("button", { name: "Descartar" }));
    expect(screen.queryByTestId("skinfold-draft-banner")).not.toBeInTheDocument();
    expect(draftKeys()).toHaveLength(0);
  });

  it("un formulario en blanco no se guarda como borrador", async () => {
    const user = userEvent.setup();
    renderWizard();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await new Promise((r) => setTimeout(r, 400));
    expect(draftKeys()).toHaveLength(0);
  });

  it("sin violaciones de accesibilidad (axe) en un paso de sitio", async () => {
    const user = userEvent.setup();
    const { container } = renderWizard();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
