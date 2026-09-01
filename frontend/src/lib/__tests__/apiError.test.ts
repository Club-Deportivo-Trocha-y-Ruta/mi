/**
 * Tests para `extractErrorDetail` (feature 036, T045).
 *
 * Regresión concreta: `AxiosError extends Error`, así que un chequeo ingenuo
 * `err instanceof Error ? err.message : fallback` SIEMPRE gana antes de
 * mirar `err.response.data.detail` — esconde el mensaje en español que el
 * backend arma con cuidado detrás de "Request failed with status code 409".
 */
import { describe, it, expect } from "vitest";

import { extractErrorDetail } from "@/lib/apiError";

/** Fabrica un objeto con forma de AxiosError (duck-typing, sin importar axios). */
function fakeAxiosError(opts: {
  status?: number;
  detail?: unknown;
  message?: string;
  hasResponse?: boolean;
}): unknown {
  const { status = 409, detail, message = `Request failed with status code ${status}`, hasResponse = true } = opts;
  return {
    isAxiosError: true,
    message,
    request: {},
    ...(hasResponse ? { response: { status, data: detail !== undefined ? { detail } : {} } } : {}),
  };
}

describe("extractErrorDetail", () => {
  it("prioriza el detail string del backend sobre err.message genérico", () => {
    const err = fakeAxiosError({
      status: 409,
      detail: "Ya hay un análisis en curso para esta válida.",
    });
    expect(extractErrorDetail(err)).toBe(
      "Ya hay un análisis en curso para esta válida.",
    );
  });

  it("no muestra nunca el mensaje genérico 'Request failed with status code N'", () => {
    const err = fakeAxiosError({
      status: 403,
      detail: "Sin permisos para lanzar análisis",
    });
    const result = extractErrorDetail(err);
    expect(result).not.toMatch(/request failed with status code/i);
    expect(result).toBe("Sin permisos para lanzar análisis");
  });

  it("usa el primer msg de un detail-array de validación Pydantic", () => {
    const err = fakeAxiosError({
      status: 422,
      detail: [{ msg: "season debe ser >= 2020", loc: ["body", "season"], type: "value_error" }],
    });
    expect(extractErrorDetail(err)).toBe("Datos inválidos: season debe ser >= 2020");
  });

  it("cae a err.message cuando no hay detail (ej. error de dominio no-HTTP)", () => {
    const err = new Error("Fallo local inesperado");
    expect(extractErrorDetail(err)).toBe("Fallo local inesperado");
  });

  it("cae al fallback provisto por el caller cuando no hay detail ni message útil", () => {
    const err = { isAxiosError: true, response: { status: 500, data: {} } };
    expect(extractErrorDetail(err, "Copy de respaldo del caller")).toBe(
      "Copy de respaldo del caller",
    );
  });

  it("usa el fallback default cuando el caller no provee uno", () => {
    const err = { isAxiosError: true, response: { status: 500, data: {} } };
    expect(extractErrorDetail(err)).toBe("Ocurrió un error. Intenta de nuevo.");
  });

  // ---------------------------------------------------------------------------
  // Cold start (Render Free despertando) — prioridad sobre el detail técnico.
  // ---------------------------------------------------------------------------
  it("una petición sin respuesta (forma cold-start) devuelve la copy calmada, no un mensaje técnico", () => {
    const err = fakeAxiosError({ hasResponse: false, message: "Network Error" });
    expect(extractErrorDetail(err)).toBe(
      "La aplicación está iniciando, puede tardar unos segundos. Intenta de nuevo en un momento.",
    );
  });

  it("un 409 CON respuesta y detail normal NO se confunde con cold start", () => {
    // Guarda contra una regresión donde el chequeo de cold start fuera
    // demasiado agresivo y se comiera el detail de un error HTTP normal.
    const err = fakeAxiosError({
      status: 409,
      detail: "Ya existe un resumen de temporada reciente para este atleta.",
    });
    expect(extractErrorDetail(err)).toBe(
      "Ya existe un resumen de temporada reciente para este atleta.",
    );
  });

  it("string plano se devuelve tal cual", () => {
    expect(extractErrorDetail("boom")).toBe("boom");
  });

  it("null/undefined caen al fallback", () => {
    expect(extractErrorDetail(null, "respaldo")).toBe("respaldo");
    expect(extractErrorDetail(undefined, "respaldo")).toBe("respaldo");
  });
});
