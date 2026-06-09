import { describe, it, expect } from "vitest";

import { buildEventPayload, type CalendarEventFormValues } from "./calendar.schema";

// Base values mínimos válidos para construir un payload de competition.
function baseValues(
  overrides: Partial<CalendarEventFormValues> = {},
): CalendarEventFormValues {
  return {
    event_type: "competition",
    title: "Copa Valle — Válida V Palmira",
    description: "",
    location: "Palmira",
    start_date: "2026-08-01",
    start_time: "07:00",
    duration_min: 120,
    all_day: false,
    color_hex: "",
    race_event_id: 5,
    audiences: [{ audience_type: "all_club", audience_value: {} }],
    data_competition: { city: "Palmira", race_category: "B", is_departmental: false },
    data_training_session: undefined,
    data_club_event: undefined,
    data_personal_training: undefined,
    data_group_training: undefined,
    data_rest_day: undefined,
    ...overrides,
  } as CalendarEventFormValues;
}

describe("buildEventPayload — all_day timestamps (feature 008 fix #2)", () => {
  it("all_day=true envía límites de día naive en hora local (sin desplazamiento UTC)", () => {
    const payload = buildEventPayload(baseValues({ all_day: true }));

    // Debe coincidir EXACTAMENTE con la ruta backend one-click
    // (create_linked_calendar_event → 00:00:00 / 23:59:59 naive America/Bogota).
    expect(payload.start_at).toBe("2026-08-01T00:00:00");
    expect(payload.end_at).toBe("2026-08-01T23:59:59");
    // Sin sufijo 'Z' ni offset: no se convierte a UTC (evita el day-shift que
    // producía toISOString() según la zona del navegador).
    expect(payload.start_at).not.toMatch(/Z$/);
    expect(payload.end_at).not.toMatch(/Z$/);
    expect(payload.all_day).toBe(true);
  });

  it("evento con hora (all_day=false) conserva el comportamiento UTC ISO", () => {
    const payload = buildEventPayload(baseValues({ all_day: false }));
    expect(payload.start_at).toMatch(/Z$/);
    expect(payload.end_at).toMatch(/Z$/);
  });
});
