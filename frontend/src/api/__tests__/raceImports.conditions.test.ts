/**
 * Tests F-COND para api client de race-imports.
 *
 * Verifica que `parseRaceImport` serializa correctamente los 5 campos de
 * condiciones de carrera al multipart `FormData`:
 *  - Strings vacíos / null / undefined → SE OMITEN del FormData.
 *  - Valores presentes → se envían como string (FormData no acepta number).
 *
 * Importante: NO testeamos la integración con axios (eso es responsabilidad
 * del interceptor de apiClient). Solo verificamos la construcción del payload.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import * as clientModule from "@/api/client";
import { parseRaceImport } from "@/api/raceImports";
import type { ImportParseRequestFields } from "@/types/raceImports.types";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: {
    post: ReturnType<typeof vi.fn>;
  };
};

function makePdf(): File {
  return new File([new Uint8Array(64)], "test.pdf", {
    type: "application/pdf",
  });
}

const BASE_FIELDS: ImportParseRequestFields = {
  series_name: "Copa Valle",
  season: 2026,
  valida_num: 4,
  event_name: "IV — Cali",
  event_date: "2026-05-17",
  location: "Cali",
};

beforeEach(() => {
  mockApi.post.mockReset();
  mockApi.post.mockResolvedValue({ data: { parse_id: "p-1" } });
});

/** Helper — extrae el FormData del primer call de apiClient.post. */
function getSentFormData(): FormData {
  const [, body] = mockApi.post.mock.calls[0];
  expect(body).toBeInstanceOf(FormData);
  return body as FormData;
}

describe("parseRaceImport — campos obligatorios siempre presentes", () => {
  it("envía los 6 campos base (series, season, valida, event_name, date, location)", async () => {
    await parseRaceImport(BASE_FIELDS, { resultadosPdf: makePdf() });

    const fd = getSentFormData();
    expect(fd.get("series_name")).toBe("Copa Valle");
    expect(fd.get("season")).toBe("2026");
    expect(fd.get("valida_num")).toBe("4");
    expect(fd.get("event_name")).toBe("IV — Cali");
    expect(fd.get("event_date")).toBe("2026-05-17");
    expect(fd.get("location")).toBe("Cali");
  });
});

describe("parseRaceImport — F-COND: condiciones vacías se omiten", () => {
  it("ningún campo de condición presente → FormData NO los contiene", async () => {
    await parseRaceImport(BASE_FIELDS, { resultadosPdf: makePdf() });

    const fd = getSentFormData();
    expect(fd.has("climate")).toBe(false);
    expect(fd.has("temperature_c")).toBe(false);
    expect(fd.has("surface_condition")).toBe(false);
    expect(fd.has("altitude_msnm")).toBe(false);
    expect(fd.has("weather_notes")).toBe(false);
  });

  it("campos en null → se omiten (no se serializan como 'null')", async () => {
    await parseRaceImport(
      {
        ...BASE_FIELDS,
        climate: null,
        temperature_c: null,
        surface_condition: null,
        altitude_msnm: null,
        weather_notes: null,
      },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    expect(fd.has("climate")).toBe(false);
    expect(fd.has("temperature_c")).toBe(false);
    expect(fd.has("surface_condition")).toBe(false);
    expect(fd.has("altitude_msnm")).toBe(false);
    expect(fd.has("weather_notes")).toBe(false);
  });

  it("strings vacíos en climate/temperature_c/weather_notes → se omiten", async () => {
    await parseRaceImport(
      {
        ...BASE_FIELDS,
        climate: "",
        temperature_c: "",
        weather_notes: "",
      },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    expect(fd.has("climate")).toBe(false);
    expect(fd.has("temperature_c")).toBe(false);
    expect(fd.has("weather_notes")).toBe(false);
  });
});

describe("parseRaceImport — F-COND: condiciones presentes se envían", () => {
  it("los 5 campos llenos se incluyen serializados como string", async () => {
    await parseRaceImport(
      {
        ...BASE_FIELDS,
        climate: "Soleado",
        temperature_c: 22.5,
        surface_condition: "barro",
        altitude_msnm: 1340,
        weather_notes: "Pista lavada",
      },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    expect(fd.get("climate")).toBe("Soleado");
    expect(fd.get("temperature_c")).toBe("22.5");
    expect(fd.get("surface_condition")).toBe("barro");
    expect(fd.get("altitude_msnm")).toBe("1340");
    expect(fd.get("weather_notes")).toBe("Pista lavada");
  });

  it("temperature_c como string también se envía", async () => {
    await parseRaceImport(
      {
        ...BASE_FIELDS,
        temperature_c: "18.3",
      },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    expect(fd.get("temperature_c")).toBe("18.3");
  });

  it("altitude_msnm=0 sí se envía (no se confunde con null)", async () => {
    await parseRaceImport(
      {
        ...BASE_FIELDS,
        altitude_msnm: 0,
      },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    // Bug guard: `if (val != null)` debe permitir 0 (porque `0 != null`).
    expect(fd.get("altitude_msnm")).toBe("0");
  });

  it("temperature_c=0 sí se envía (cota inferior válida)", async () => {
    await parseRaceImport(
      {
        ...BASE_FIELDS,
        temperature_c: 0,
      },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    expect(fd.get("temperature_c")).toBe("0");
  });
});

describe("parseRaceImport — coexistencia con general PDF", () => {
  it("se envía general_pdf si se pasa, y se omite si no", async () => {
    const general = new File([new Uint8Array(32)], "general.pdf", {
      type: "application/pdf",
    });
    await parseRaceImport(
      { ...BASE_FIELDS, kind: "both", surface_condition: "seca" },
      { resultadosPdf: makePdf(), generalPdf: general },
    );

    const fd = getSentFormData();
    expect(fd.get("general_pdf")).toBeInstanceOf(File);
    expect(fd.get("kind")).toBe("both");
    expect(fd.get("surface_condition")).toBe("seca");
  });

  it("sin general_pdf → no aparece en el FormData", async () => {
    await parseRaceImport(
      { ...BASE_FIELDS, surface_condition: "humeda" },
      { resultadosPdf: makePdf() },
    );

    const fd = getSentFormData();
    expect(fd.has("general_pdf")).toBe(false);
    expect(fd.get("surface_condition")).toBe("humeda");
  });
});
