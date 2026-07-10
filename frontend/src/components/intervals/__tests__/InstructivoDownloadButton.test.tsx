/**
 * Tests para InstructivoDownloadButton (feature 026, US3):
 *   - Selector de marca con las tres opciones (Garmin/Magene/iGPSport),
 *     "garmin" por defecto.
 *   - `hasStructure=false` deshabilita selector + botón y muestra el copy
 *     explicativo (espeja el guard 404 del servidor).
 *   - Click dispara `useDownloadInstructivo().mutate` con
 *     `{ trainingSessionId, brand }`; en éxito entrega el blob a
 *     `triggerBlobDownload` con el nombre de archivo
 *     `instructivo_{marca}_{fecha}.pdf`.
 *   - En error, muestra el mensaje mapeado por `mapIntervalError` con
 *     `role="alert"`, enlazado vía `aria-describedby`.
 *   - `isPending`: botón "Generando…" deshabilitado, selector deshabilitado.
 *   - a11y: jest-axe sin violaciones en los estados relevantes.
 *
 * Estrategia de mock: `useDownloadInstructivo` y `triggerBlobDownload` se
 * mockean a nivel de módulo (mirror de `InsightsTabAnalyze.test.tsx`) — el
 * componente no debe hacer red real; `mapIntervalError` se usa real (función
 * pura, sin red).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

const mockMutate = vi.fn();
let mockIsPending = false;
vi.mock("@/hooks/intervals/useIntervals", () => ({
  useDownloadInstructivo: () => ({
    mutate: mockMutate,
    isPending: mockIsPending,
  }),
}));

const mockTriggerBlobDownload = vi.fn();
vi.mock("@/lib/download", () => ({
  triggerBlobDownload: (...args: unknown[]) => mockTriggerBlobDownload(...args),
}));

import { InstructivoDownloadButton } from "../InstructivoDownloadButton";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FAKE_BLOB = new Blob(["%PDF-1.4 contenido ficticio"], {
  type: "application/pdf",
});

/** Error mapeable por `mapIntervalError` (404 → "No se encontró..."). */
const NOT_FOUND_ERROR = {
  isAxiosError: true,
  response: { status: 404, data: {} },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
});

function renderButton(overrides: Partial<{
  trainingSessionId: number;
  hasStructure: boolean;
  sessionDate: string;
}> = {}) {
  const props = {
    trainingSessionId: 42,
    ...overrides,
  };
  return render(<InstructivoDownloadButton {...props} />);
}

// ---------------------------------------------------------------------------
// Suite: selector de marca
// ---------------------------------------------------------------------------

describe("InstructivoDownloadButton — selector de marca", () => {
  it("renderiza el selector 'Dispositivo' con las tres marcas y 'garmin' por defecto", () => {
    renderButton();

    const select = screen.getByLabelText("Dispositivo") as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.text);
    expect(labels).toEqual(["Garmin", "Magene", "iGPSport"]);
    expect(select).toHaveValue("garmin");
  });

  it("cambiar la marca actualiza el valor seleccionado", async () => {
    const user = userEvent.setup();
    renderButton();

    await user.selectOptions(screen.getByLabelText("Dispositivo"), "magene");

    expect(screen.getByLabelText("Dispositivo")).toHaveValue("magene");
  });
});

// ---------------------------------------------------------------------------
// Suite: hasStructure=false
// ---------------------------------------------------------------------------

describe("InstructivoDownloadButton — sin estructura", () => {
  it("deshabilita el selector y el botón, y muestra el copy explicativo", () => {
    renderButton({ hasStructure: false });

    expect(screen.getByLabelText("Dispositivo")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Agregá una estructura de intervalos a la sesión para descargar el instructivo.",
      ),
    ).toBeInTheDocument();
  });

  it("no llama a mutate al clicar el botón deshabilitado", async () => {
    const user = userEvent.setup();
    renderButton({ hasStructure: false });

    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("con hasStructure=true (por defecto) no muestra el copy explicativo", () => {
    renderButton({ hasStructure: true });

    expect(
      screen.queryByText(/Agregá una estructura de intervalos/),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: descarga exitosa
// ---------------------------------------------------------------------------

describe("InstructivoDownloadButton — descarga exitosa", () => {
  it("clicar 'Descargar instructivo' llama a mutate con trainingSessionId y brand", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_vars, opts) => opts.onSuccess(FAKE_BLOB));
    renderButton({ trainingSessionId: 42 });

    await user.selectOptions(screen.getByLabelText("Dispositivo"), "igpsport");
    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(mockMutate).toHaveBeenCalledWith(
      { trainingSessionId: 42, brand: "igpsport" },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("en éxito entrega el blob a triggerBlobDownload con el nombre de archivo esperado", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_vars, opts) => opts.onSuccess(FAKE_BLOB));
    renderButton({ sessionDate: "2026-07-08" });

    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(mockTriggerBlobDownload).toHaveBeenCalledWith(
      FAKE_BLOB,
      "instructivo_garmin_2026-07-08.pdf",
    );
  });

  it("usa la marca seleccionada en el nombre del archivo", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_vars, opts) => opts.onSuccess(FAKE_BLOB));
    renderButton({ sessionDate: "2026-07-08" });

    await user.selectOptions(screen.getByLabelText("Dispositivo"), "magene");
    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(mockTriggerBlobDownload).toHaveBeenCalledWith(
      FAKE_BLOB,
      "instructivo_magene_2026-07-08.pdf",
    );
  });
});

// ---------------------------------------------------------------------------
// Suite: descarga con error
// ---------------------------------------------------------------------------

describe("InstructivoDownloadButton — descarga con error", () => {
  it("muestra el mensaje mapeado con role=alert cuando la mutación falla", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_vars, opts) => opts.onError(NOT_FOUND_ERROR));
    renderButton();

    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se encontró la estructura o recurso solicitado.",
    );
  });

  it("no muestra role=alert antes de intentar la descarga", () => {
    renderButton();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("el botón queda enlazado al error vía aria-describedby", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_vars, opts) => opts.onError(NOT_FOUND_ERROR));
    renderButton();

    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    const alert = screen.getByRole("alert");
    const button = screen.getByRole("button", { name: "Descargar instructivo" });
    expect(button).toHaveAttribute("aria-describedby", alert.id);
  });

  it("un nuevo intento limpia el mensaje de error previo antes de mutar de nuevo", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementationOnce((_vars, opts) =>
      opts.onError(NOT_FOUND_ERROR),
    );
    renderButton();

    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();

    mockMutate.mockImplementationOnce((_vars, opts) => opts.onSuccess(FAKE_BLOB));
    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: isPending
// ---------------------------------------------------------------------------

describe("InstructivoDownloadButton — isPending", () => {
  it("muestra 'Generando…' y deshabilita el botón y el selector", () => {
    mockIsPending = true;
    renderButton();

    expect(
      screen.getByRole("button", { name: "Generando…" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Dispositivo")).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("InstructivoDownloadButton — accesibilidad", () => {
  it("no tiene violaciones de a11y en el estado por defecto", async () => {
    const { container } = renderButton();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con hasStructure=false", async () => {
    const { container } = renderButton({ hasStructure: false });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con un error visible", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_vars, opts) => opts.onError(NOT_FOUND_ERROR));
    const { container } = renderButton();

    await user.click(
      screen.getByRole("button", { name: "Descargar instructivo" }),
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y cuando isPending=true", async () => {
    mockIsPending = true;
    const { container } = renderButton();
    expect(await axe(container)).toHaveNoViolations();
  });
});
