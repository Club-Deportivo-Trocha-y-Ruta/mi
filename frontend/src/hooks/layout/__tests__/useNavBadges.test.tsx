/**
 * Tests de `useNavBadges` (feature 035).
 *
 * Cubre el filtrado de cada fuente (mismos criterios que `PendingInbox`) y el
 * contrato de "sin insignia": cargando, con error o en cero → `undefined`.
 * Las queries subyacentes se mockean: aquí se prueba la derivación, no el
 * transporte (eso ya lo cubren los tests de `useRaceEvents` y
 * `useNewsletterStatusSummary`).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import type { RaceEventListItem } from "@/types/raceEvents.types";
import type { NewsletterStatusSummaryItem } from "@/hooks/training/useNewsletterStatusSummary";

const mockUseRaceEventsList = vi.hoisted(() => vi.fn());
const mockUseNewsletterStatusSummary = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/race/useRaceEvents", () => ({
  useRaceEventsList: mockUseRaceEventsList,
}));

vi.mock("@/hooks/training/useNewsletterStatusSummary", () => ({
  useNewsletterStatusSummary: mockUseNewsletterStatusSummary,
}));

import { useNavBadges } from "@/hooks/layout/useNavBadges";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Fecha ISO desplazada N días respecto de hoy (±5 días evita el borde de TZ). */
function isoDaysFromToday(days: number): string {
  const d = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10);
}

function raceItem(overrides: Partial<RaceEventListItem>): RaceEventListItem {
  return {
    id: 1,
    series_id: 1,
    sequence_number: 1,
    name: "Válida",
    event_date: isoDaysFromToday(-5),
    location: null,
    is_championship: false,
    status: "scheduled",
    has_results: false,
    has_calendar_event: false,
    conditions_completeness: "empty",
    ...overrides,
  } as RaceEventListItem;
}

function newsletterItem(
  status: NewsletterStatusSummaryItem["status"],
  athleteId: number,
): NewsletterStatusSummaryItem {
  return {
    athlete_id: athleteId,
    newsletter_id: athleteId,
    status,
    generated_at: "2026-08-01T00:00:00Z",
    sent_at: status === "sent" ? "2026-08-02T00:00:00Z" : null,
  };
}

function mockRaces(items: RaceEventListItem[]) {
  mockUseRaceEventsList.mockReturnValue({
    data: { items, total: items.length },
    isSuccess: true,
  });
}

function mockNewsletters(items: NewsletterStatusSummaryItem[]) {
  mockUseNewsletterStatusSummary.mockReturnValue({
    data: { year: 2026, month: 8, items },
    isSuccess: true,
  });
}

/** Fuente aún cargando o caída: sin `data` y sin éxito. */
const NOT_READY = { data: undefined, isSuccess: false } as const;

beforeEach(() => {
  vi.clearAllMocks();
  mockUseRaceEventsList.mockReturnValue(NOT_READY);
  mockUseNewsletterStatusSummary.mockReturnValue(NOT_READY);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useNavBadges — Competencias (resultados por importar)", () => {
  it("cuenta sólo válidas ya corridas y sin resultados", () => {
    mockRaces([
      raceItem({ id: 1, event_date: isoDaysFromToday(-10), has_results: false }),
      raceItem({ id: 2, event_date: isoDaysFromToday(-5), has_results: false }),
      // Ya importada → no cuenta.
      raceItem({ id: 3, event_date: isoDaysFromToday(-3), has_results: true }),
      // Todavía no ocurre → no cuenta.
      raceItem({ id: 4, event_date: isoDaysFromToday(15), has_results: false }),
    ]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.competitions).toBe(2);
  });

  // Nota: `diffDaysFromToday` interpreta una fecha sin hora como medianoche
  // UTC y la reproyecta a America/Bogota (UTC-5), así que el "día 0" del
  // club corresponde a +1 en ISO. Se prueba el lado seguro del umbral: una
  // válida que todavía no ocurrió nunca produce insignia.
  it("una válida que aún no ocurre no cuenta como pendiente", () => {
    mockRaces([
      raceItem({ id: 1, event_date: isoDaysFromToday(1), has_results: false }),
    ]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.competitions).toBeUndefined();
  });

  it("cero pendientes no produce insignia (nunca un '0')", () => {
    mockRaces([raceItem({ id: 1, has_results: true })]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.competitions).toBeUndefined();
  });

  it("mientras la fuente carga o falla no hay insignia", () => {
    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.competitions).toBeUndefined();
    expect(result.current.families).toBeUndefined();
  });

  it("una fecha inválida no se cuenta como pendiente", () => {
    mockRaces([raceItem({ id: 1, event_date: "", has_results: false })]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.competitions).toBeUndefined();
  });
});

describe("useNavBadges — Familias (boletines pendientes del mes)", () => {
  it("cuenta los boletines cuyo estado no es 'sent'", () => {
    mockNewsletters([
      newsletterItem("draft", 1),
      newsletterItem("approved", 2),
      newsletterItem("sent", 3),
    ]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.families).toBe(2);
  });

  it("todos enviados → sin insignia", () => {
    mockNewsletters([newsletterItem("sent", 1), newsletterItem("sent", 2)]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.families).toBeUndefined();
  });

  it("el resumen vacío no produce insignia", () => {
    mockNewsletters([]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current.families).toBeUndefined();
  });
});

describe("useNavBadges — visibilidad por rol", () => {
  it("admin también recibe ambas insignias (ve Competencias y Familias)", () => {
    mockRaces([raceItem({ id: 1, has_results: false })]);
    mockNewsletters([newsletterItem("draft", 1)]);

    const { result } = renderHook(() => useNavBadges("admin"));

    expect(result.current).toEqual({ competitions: 1, families: 1 });
  });

  it("sólo devuelve claves de áreas con pendientes reales", () => {
    mockRaces([raceItem({ id: 1, has_results: true })]);
    mockNewsletters([newsletterItem("draft", 1), newsletterItem("draft", 2)]);

    const { result } = renderHook(() => useNavBadges("coach"));

    expect(result.current).toEqual({ families: 2 });
  });
});
