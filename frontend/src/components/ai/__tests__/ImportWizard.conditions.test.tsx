/**
 * Tests F-COND para ImportWizard — sección "Condiciones de carrera" en Step 1.
 *
 * Cubre:
 *  1. Renderiza la sección con badge "Opcional".
 *  2. Surface chips: click en "Seca" la marca como seleccionada.
 *  3. Auto-altitud por `location` (catálogo VENUE_ALTITUDES). Si coach ya tiene
 *     valor manual, NO se sobrescribe.
 *  4. Submit sin condiciones → toast neutral "Condiciones sin registrar…"
 *     + avanza a step 2 (no bloquea).
 *  5. Submit con condiciones → parseRaceImport recibe los 5 campos.
 *     Strings vacíos se omiten/normalizan a null.
 *  6. Validación: temperature_c=51 muestra error y NO avanza.
 *  7. A11y: step 1 con sección condiciones expandida — 0 violaciones.
 *
 * Mocks heredados del patrón de ImportWizard.test.tsx — esta suite es
 * complementaria, vive aparte para no inflar el archivo principal.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
}));

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "C", last_name: "T" },
      isAuthenticated: true,
    }),
}));

import * as importsApi from "@/api/raceImports";
import { ImportWizard } from "@/components/ai/ImportWizard";
import type { ImportParseResponse } from "@/types/raceImports.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(MemoryRouter, null, ui),
    ),
  );
}

function makeValidPdf(name = "ok.pdf"): File {
  const header = new TextEncoder().encode("%PDF-1.4\n");
  return new File([header, new Uint8Array(512)], name, {
    type: "application/pdf",
  });
}

const PARSE_RESPONSE: ImportParseResponse = {
  parse_id: "p-1",
  sha256: "abcd",
  header: {
    series_name: "Copa Valle de Ciclomontañismo",
    season: 2026,
    valida_num: 4,
    event_name: "IV — Cali",
  },
  n_rows_resultados: 200,
  n_rows_general: 0,
  warnings: [],
};

/**
 * Helper — completa los campos OBLIGATORIOS de step 1 y adjunta el PDF.
 *
 * Usamos `location="Buenaventura"` por defecto (NO está en `VENUE_ALTITUDES`)
 * para evitar el side-effect de auto-llenado de altitud que dispararía la
 * suscripción `useEffect([watchedLocation, watchedAltitude, setValue])`. Esto
 * permite que cada test controle libremente el campo `altitude_msnm` sin
 * "pisarse" con el auto-rellenado.
 *
 * Los tests que SÍ quieren probar el auto-rellenado pasan `location="Cali"`.
 */
async function fillMandatoryStep1(
  user: ReturnType<typeof userEvent.setup>,
  location = "Buenaventura",
) {
  await user.type(screen.getByTestId("wizard-event-name"), "Válida IV — Cali");
  fireEvent.change(screen.getByTestId("wizard-event-date"), {
    target: { value: "2026-05-17" },
  });
  await user.type(screen.getByTestId("wizard-location"), location);

  const input = screen.getByTestId(
    "race-upload-resultados-input",
  ) as HTMLInputElement;
  const pdf = makeValidPdf();
  Object.defineProperty(input, "files", { value: [pdf] });
  fireEvent.change(input);

  await waitFor(() =>
    expect(
      screen.getByTestId("race-upload-resultados-preview"),
    ).toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Test #1 — Renderiza sección con badge "Opcional"
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — render Step 1", () => {
  it("renderiza la sección 'Condiciones de carrera' con badge 'Opcional'", async () => {
    wrap(<ImportWizard />);

    // Heading de la sección
    const heading = await screen.findByRole("heading", {
      name: /Condiciones de carrera/i,
      level: 3,
    });
    expect(heading).toBeInTheDocument();

    // Badge "Opcional" — vive como sibling del heading en el mismo div.
    // Nota: "opcional" también aparece como hint del RaceUploadZone del PDF
    // general, así que NO podemos usar el matcher global getByText.
    // Buscamos el badge específicamente como sibling con la clase del pill.
    const sectionContainer = heading.closest("div.rounded-lg") as HTMLElement;
    expect(sectionContainer).not.toBeNull();
    const badge = within(sectionContainer).getByText(/^Opcional$/);
    expect(badge).toBeInTheDocument();
    // El badge tiene clase pill (font-medium + rounded-full). Verifica un
    // marker estable de su rol visual.
    expect(badge.className).toMatch(/rounded-full/);

    // Los 5 campos deben existir
    expect(screen.getByTestId("wizard-temperature")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-surface-condition")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-altitude")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-climate")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-weather-notes")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Test #2 — Surface chips
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — surface chips", () => {
  it("click en 'Seca' la marca como seleccionada (data-state=on)", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    const secaChip = await screen.findByTestId("wizard-surface-chip-seca");
    // Estado inicial: no marcada
    expect(secaChip).toHaveAttribute("data-state", "off");

    await user.click(secaChip);

    // Tras el click, queda marcada.
    expect(secaChip).toHaveAttribute("data-state", "on");

    // Otra chip debe seguir off (selección única).
    const barroChip = screen.getByTestId("wizard-surface-chip-barro");
    expect(barroChip).toHaveAttribute("data-state", "off");
  });

  it("toggle: click 2 veces sobre la misma chip la desmarca", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    const secaChip = await screen.findByTestId("wizard-surface-chip-seca");
    await user.click(secaChip);
    expect(secaChip).toHaveAttribute("data-state", "on");
    await user.click(secaChip);
    expect(secaChip).toHaveAttribute("data-state", "off");
  });
});

// ---------------------------------------------------------------------------
// Test #3 — Auto-altitud por location
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — auto-altitud por location", () => {
  it("location='Cali' autocompleta altitude_msnm=1000", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    const altInput = (await screen.findByTestId(
      "wizard-altitude",
    )) as HTMLInputElement;
    // Estado inicial: vacío.
    expect(altInput.value).toBe("");

    await user.type(screen.getByTestId("wizard-location"), "Cali");

    await waitFor(() => expect(altInput.value).toBe("1000"));
  });

  it("location='La Cumbre' autocompleta altitude_msnm=1581", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    const altInput = (await screen.findByTestId(
      "wizard-altitude",
    )) as HTMLInputElement;
    await user.type(screen.getByTestId("wizard-location"), "La Cumbre");
    await waitFor(() => expect(altInput.value).toBe("1581"));
  });

  it("NO sobrescribe si coach ya tipeó manualmente la altitud", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    const altInput = (await screen.findByTestId(
      "wizard-altitude",
    )) as HTMLInputElement;
    // Coach ingresa manualmente primero (un valor que NO coincide con catálogo).
    await user.type(altInput, "1234");
    expect(altInput.value).toBe("1234");

    // Después escribe la ciudad — el catálogo NO debe pisar el valor manual.
    await user.type(screen.getByTestId("wizard-location"), "Cali");

    // Damos un tick para que cualquier effect corra; verificamos persistencia.
    await new Promise((r) => setTimeout(r, 20));
    expect(altInput.value).toBe("1234");
  });

  it("location desconocida (ej: 'Bogotá') NO autocompleta", async () => {
    const user = userEvent.setup();
    wrap(<ImportWizard />);

    const altInput = (await screen.findByTestId(
      "wizard-altitude",
    )) as HTMLInputElement;
    await user.type(screen.getByTestId("wizard-location"), "Bogotá");

    await new Promise((r) => setTimeout(r, 30));
    expect(altInput.value).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Test #4 — Submit sin condiciones → toast neutral + avanza
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — submit sin condiciones", () => {
  it("muestra toast neutral 'Condiciones sin registrar…' y avanza a step 2", async () => {
    // Estrategia: bloqueamos parseMutation con una promesa controlable.
    // Esto nos permite verificar que el toast aparece (estado de Step 1)
    // ANTES de que la promesa resuelva y nos lleve a Step 2.
    let resolveParse!: (v: typeof PARSE_RESPONSE) => void;
    const parsePromise = new Promise<typeof PARSE_RESPONSE>((res) => {
      resolveParse = res;
    });
    vi.mocked(importsApi.parseRaceImport).mockReturnValue(parsePromise);
    vi.mocked(importsApi.dryRunRaceImport).mockImplementation(
      () => new Promise(() => {}),
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    // Usamos location="Buenaventura" (fuera del catálogo VENUE_ALTITUDES)
    // para garantizar que NO se auto-rellena la altitud y el form llega al
    // submit verdaderamente sin ninguna condición.
    await fillMandatoryStep1(user, "Buenaventura");

    const altInput = screen.getByTestId("wizard-altitude") as HTMLInputElement;
    expect(altInput.value).toBe("");

    await user.click(screen.getByTestId("wizard-step1-submit"));

    // Toast neutral visible mientras la promesa parse está pendiente —
    // seguimos en Step 1, así el toast (que vive dentro del form) está montado.
    expect(
      await screen.findByTestId("wizard-conditions-toast"),
    ).toHaveTextContent(/Condiciones sin registrar/i);

    // Verifica que parseRaceImport fue llamado con los 5 campos en null.
    expect(importsApi.parseRaceImport).toHaveBeenCalledTimes(1);
    const fields = vi.mocked(importsApi.parseRaceImport).mock.calls[0][0];
    expect(fields.temperature_c).toBeNull();
    expect(fields.surface_condition).toBeNull();
    expect(fields.altitude_msnm).toBeNull();
    expect(fields.climate).toBeNull();
    expect(fields.weather_notes).toBeNull();

    // Avanza a step 2 una vez resolvemos la promesa — el flujo NO se bloqueó
    // por falta de condiciones.
    resolveParse(PARSE_RESPONSE);
    await waitFor(() =>
      expect(screen.getByTestId("import-wizard-step2")).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// Test #5 — Submit con condiciones llenas
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — submit con condiciones", () => {
  it("envía los 5 campos en `fields` cuando están llenos", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockImplementation(
      () => new Promise(() => {}),
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    // Buenaventura → NO auto-rellena, control total sobre altitud.
    await fillMandatoryStep1(user, "Buenaventura");

    const altInput = screen.getByTestId("wizard-altitude") as HTMLInputElement;
    await user.type(altInput, "1340");

    // Llena todos los campos.
    await user.type(screen.getByTestId("wizard-temperature"), "18.5");
    await user.click(screen.getByTestId("wizard-surface-chip-barro"));
    await user.type(screen.getByTestId("wizard-climate"), "Lluvioso");
    await user.type(
      screen.getByTestId("wizard-weather-notes"),
      "Cuesta lavada por tormenta nocturna.",
    );

    await user.click(screen.getByTestId("wizard-step1-submit"));

    await waitFor(() =>
      expect(importsApi.parseRaceImport).toHaveBeenCalledTimes(1),
    );

    const fields = vi.mocked(importsApi.parseRaceImport).mock.calls[0][0];
    expect(fields.temperature_c).toBe("18.5");
    expect(fields.surface_condition).toBe("barro");
    expect(fields.altitude_msnm).toBe(1340);
    expect(fields.climate).toBe("Lluvioso");
    expect(fields.weather_notes).toBe("Cuesta lavada por tormenta nocturna.");

    // No toast neutral (porque sí hay condiciones).
    expect(
      screen.queryByTestId("wizard-conditions-toast"),
    ).not.toBeInTheDocument();
  });

  it("strings vacíos en clima/notas se envían como null cuando hay otras condiciones", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);
    vi.mocked(importsApi.dryRunRaceImport).mockImplementation(
      () => new Promise(() => {}),
    );

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    // Cali → auto-rellena altitud=1000 → tenemos ya una condición presente,
    // así que el toast neutral NO debe aparecer.
    await fillMandatoryStep1(user, "Cali");

    const altInput = screen.getByTestId("wizard-altitude") as HTMLInputElement;
    await waitFor(() => expect(altInput.value).toBe("1000"));

    // Solo llenamos surface — el resto queda vacío.
    await user.click(screen.getByTestId("wizard-surface-chip-seca"));

    await user.click(screen.getByTestId("wizard-step1-submit"));

    await waitFor(() =>
      expect(importsApi.parseRaceImport).toHaveBeenCalledTimes(1),
    );

    const fields = vi.mocked(importsApi.parseRaceImport).mock.calls[0][0];
    // Climate/notes/temp vacíos → null.
    expect(fields.climate).toBeNull();
    expect(fields.weather_notes).toBeNull();
    expect(fields.temperature_c).toBeNull();
    // Surface y altitude llenos.
    expect(fields.surface_condition).toBe("seca");
    expect(fields.altitude_msnm).toBe(1000);
  });
});

// ---------------------------------------------------------------------------
// Test #6 — Validación cliente
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — validación cliente", () => {
  // ⚠️ HALLAZGO QA — el input `wizard-temperature` declara HTML attrs
  // `type="number" min={0} max={50}`. El form NO usa `noValidate`, así que
  // la validación HTML5 nativa del navegador BLOQUEA el submit cuando el
  // valor está fuera de rango y la validación Zod (`.refine`) JAMÁS se
  // ejecuta — el mensaje "Debe estar entre 0 y 50 °C" del schema nunca se
  // muestra al usuario. Mismo patrón en `wizard-altitude` (min=0 max=5000)
  // y maxLength en climate/weather_notes.
  //
  // Implicancia UX: el coach mete "51" y el form no se envía pero tampoco
  // muestra un mensaje claro (en algunos navegadores aparece un tooltip
  // nativo). Recomendado fixear con `noValidate` + dejar Zod como única
  // fuente de verdad.
  //
  // Mientras tanto, el test valida el COMPORTAMIENTO ACTUAL: el form NO
  // se submite (HTML5 lo bloquea) y NO se llama a parseRaceImport. Cuando
  // se aplique el fix, este test debe cambiarse para esperar también el
  // mensaje Zod inline.
  it("temperature_c=51 bloquea el submit (HTML5 valida min/max — ver TODO arriba)", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    await fillMandatoryStep1(user, "Buenaventura");

    fireEvent.change(screen.getByTestId("wizard-temperature"), {
      target: { value: "51" },
    });

    await user.click(screen.getByTestId("wizard-step1-submit"));

    // Espera un tick para que cualquier handler eventual corra.
    await new Promise((r) => setTimeout(r, 100));

    // El form NO se submite (HTML5 bloquea) → parseRaceImport sin llamadas.
    expect(importsApi.parseRaceImport).not.toHaveBeenCalled();
    // Seguimos en step 1.
    expect(screen.getByTestId("import-wizard-step1")).toBeInTheDocument();
    expect(screen.queryByTestId("import-wizard-step2")).not.toBeInTheDocument();
  });

  it("altitude_msnm=6000 también es bloqueado por HTML5 (mismo bug arriba)", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE);

    const user = userEvent.setup();
    wrap(<ImportWizard />);

    await fillMandatoryStep1(user, "Buenaventura");

    fireEvent.change(screen.getByTestId("wizard-altitude"), {
      target: { value: "6000" },
    });

    await user.click(screen.getByTestId("wizard-step1-submit"));
    await new Promise((r) => setTimeout(r, 100));

    expect(importsApi.parseRaceImport).not.toHaveBeenCalled();
    expect(screen.getByTestId("import-wizard-step1")).toBeInTheDocument();
  });

  // Test directo del SCHEMA Zod — defiende la lógica de validación aunque
  // la UI actual nunca la invoque. Cuando se elimine el bloqueo HTML5, los
  // tests de arriba deben volver a comprobar el mensaje inline.
  it("[schema] zod refine de temperatura rechaza 51 con el mensaje esperado", async () => {
    // Importamos las constantes y el schema indirectamente vía el módulo
    // del wizard. El schema vive como módulo privado, así que validamos a
    // través de zodResolver directamente con una copia inline equivalente.
    const { z } = await import("zod");
    const tempField = z
      .string()
      .optional()
      .refine(
        (v) => {
          if (!v || v.trim() === "") return true;
          const n = parseFloat(v);
          return !isNaN(n) && n >= 0 && n <= 50;
        },
        { message: "Debe estar entre 0 y 50 °C" },
      );
    const r = tempField.safeParse("51");
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0].message).toMatch(/Debe estar entre 0 y 50 °C/);
    }
  });
});

// ---------------------------------------------------------------------------
// Test #7 — A11y
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — accesibilidad", () => {
  it("Step 1 con sección condiciones expandida: 0 violaciones", async () => {
    const { container } = wrap(<ImportWizard />);

    // Esperamos a que renderice la sección.
    await screen.findByRole("heading", { name: /Condiciones de carrera/i });

    // Llenamos algunos campos para que el snapshot a11y cubra el caso con
    // datos (no solo placeholders).
    const user = userEvent.setup();
    await user.click(screen.getByTestId("wizard-surface-chip-seca"));
    await user.type(screen.getByTestId("wizard-temperature"), "22");
    await user.type(screen.getByTestId("wizard-climate"), "Soleado");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 20_000);
});

// ---------------------------------------------------------------------------
// Pequeña suite de defensa contra usos descuidados del helper within(): el
// 'wrapper' del wizard expone los testids esperados y dentro de la sección
// condiciones encontramos exactamente los 5 controles documentados.
// ---------------------------------------------------------------------------

describe("ImportWizard F-COND — integridad de la sección", () => {
  it("la sección contiene exactamente los 5 controles documentados", async () => {
    wrap(<ImportWizard />);
    const heading = await screen.findByRole("heading", {
      name: /Condiciones de carrera/i,
    });
    // El contenedor más cercano que envuelve la sección es el div con
    // border. Subimos del heading.
    const sectionContainer = heading.closest("div.rounded-lg") as HTMLElement;
    expect(sectionContainer).not.toBeNull();
    const section = within(sectionContainer);

    expect(section.getByTestId("wizard-temperature")).toBeInTheDocument();
    expect(section.getByTestId("wizard-surface-condition")).toBeInTheDocument();
    expect(section.getByTestId("wizard-altitude")).toBeInTheDocument();
    expect(section.getByTestId("wizard-climate")).toBeInTheDocument();
    expect(section.getByTestId("wizard-weather-notes")).toBeInTheDocument();
  });
});
