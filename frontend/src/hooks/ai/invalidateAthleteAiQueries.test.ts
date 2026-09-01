/**
 * Tests vitest — invalidateAthleteAiQueries (feature 036, T042).
 *
 * Contrato a proteger:
 *  - Invalida la lista explícita completa de claves con alcance de
 *    atleta (insights, insight-detail, runs, evolution, distribution)
 *    SOLO para el `athleteId` dado.
 *  - Invalida siempre las claves globales `club-insights-by-race` y
 *    `season-panorama`, sin filtrar por athleteId — este es el hueco que
 *    tenían `AthleteAIAnalysisTab.tsx` y `useRaceRun.ts` antes de T042.
 *  - NO invalida `athlete-activities` (Strava) ni `athlete-newsletter(s)`
 *    (boletín) — el predicate `startsWith("athlete-")` que reemplaza este
 *    helper sí las invalidaba por accidente.
 *  - Cuando `athleteId` se omite (caso `useApproveStep`, que no conoce el
 *    athlete_id del run), invalida las claves con alcance de atleta para
 *    CUALQUIER atleta.
 */
import { describe, it, expect, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { invalidateAthleteAiQueries } from "@/hooks/ai/invalidateAthleteAiQueries";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

describe("invalidateAthleteAiQueries", () => {
  it("invalida la lista explícita completa de claves con alcance de atleta, para el athleteId dado", () => {
    const qc = makeQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    void invalidateAthleteAiQueries(qc, 42);

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: {
      queryKey: unknown;
    }) => boolean;
    expect(typeof predicate).toBe("function");

    for (const base of [
      "athlete-insights",
      "athlete-insight-detail",
      "athlete-runs",
      "athlete-evolution",
      "athlete-distribution",
    ]) {
      expect(predicate({ queryKey: [base, 42, {}] })).toBe(true);
      // Otro atleta — NO debe invalidarse.
      expect(predicate({ queryKey: [base, 99, {}] })).toBe(false);
    }
  });

  it("invalida club-insights-by-race y season-panorama SIEMPRE, sin filtrar por athleteId — el hueco que tenían dos de los tres call sites antes de T042", () => {
    const qc = makeQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    void invalidateAthleteAiQueries(qc, 42);

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: {
      queryKey: unknown;
    }) => boolean;

    expect(predicate({ queryKey: ["club-insights-by-race", 7] })).toBe(true);
    expect(predicate({ queryKey: ["season-panorama", 2026, 1] })).toBe(true);
  });

  it("NO invalida claves de Strava (athlete-activities) ni de boletín (athlete-newsletter/athlete-newsletters) — el predicate startsWith('athlete-') que reemplaza sí lo hacía", () => {
    const qc = makeQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    void invalidateAthleteAiQueries(qc, 42);

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: {
      queryKey: unknown;
    }) => boolean;

    expect(predicate({ queryKey: ["athlete-activities", 42] })).toBe(false);
    expect(predicate({ queryKey: ["athlete-newsletter", 1, 42] })).toBe(false);
    expect(predicate({ queryKey: ["athlete-newsletters", 1, 42] })).toBe(
      false,
    );
  });

  it("NO invalida athlete-races — sólo cambia con la ingesta de una planilla nueva, nunca con un run de IA", () => {
    const qc = makeQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    void invalidateAthleteAiQueries(qc, 42);

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: {
      queryKey: unknown;
    }) => boolean;

    expect(predicate({ queryKey: ["athlete-races", 42, 2026] })).toBe(false);
  });

  it("sin athleteId (caso useApproveStep): invalida las claves con alcance de atleta para CUALQUIER atleta", () => {
    const qc = makeQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    void invalidateAthleteAiQueries(qc);

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: {
      queryKey: unknown;
    }) => boolean;

    expect(predicate({ queryKey: ["athlete-insights", 42, {}] })).toBe(true);
    expect(predicate({ queryKey: ["athlete-insights", 99, {}] })).toBe(true);
    // Los excluidos siguen excluidos aunque no se pase athleteId.
    expect(predicate({ queryKey: ["athlete-activities", 42] })).toBe(false);
  });

  it("ignora keys que no son arrays o cuyo primer elemento no es string", () => {
    const qc = makeQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    void invalidateAthleteAiQueries(qc, 42);

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: {
      queryKey: unknown;
    }) => boolean;

    expect(predicate({ queryKey: [42, "athlete-insights"] })).toBe(false);
    expect(predicate({ queryKey: "athlete-insights" })).toBe(false);
  });
});
