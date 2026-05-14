import { describe, it, expect } from "vitest";

import {
  FIELD_LABELS,
  diffAthleteIds,
  diffSessionValues,
} from "./sessionDiff";

describe("diffSessionValues", () => {
  const base = {
    scheduled_date: "2026-05-20",
    scheduled_start_time: "09:00",
    duration_min: 60,
    location: "Pista A",
    technical_focus: "Frenada",
    description: "x",
    route_text: "",
    strava_url: "",
  };

  it("retorna [] cuando no hubo cambios", () => {
    expect(diffSessionValues(base, base)).toEqual([]);
  });

  it("detecta cambio en un solo campo y usa el label en español", () => {
    const changes = diffSessionValues(base, { ...base, location: "Pista B" });
    expect(changes).toHaveLength(1);
    expect(changes[0]).toMatchObject({
      field: "location",
      fieldLabel: FIELD_LABELS.location,
      oldValue: "Pista A",
      newValue: "Pista B",
    });
  });

  it("detecta múltiples cambios y omite campos sin cambio", () => {
    const changes = diffSessionValues(base, {
      ...base,
      scheduled_date: "2026-06-01",
      duration_min: 90,
    });
    expect(changes.map((c) => c.field).sort()).toEqual([
      "duration_min",
      "scheduled_date",
    ]);
  });

  it("normaliza nulls/undefined a '—' para el padre", () => {
    const initial = { ...base, route_text: null };
    const current = { ...base, route_text: "Ruta nueva" };
    const changes = diffSessionValues(initial, current);
    expect(changes[0].oldValue).toBe("—");
    expect(changes[0].newValue).toBe("Ruta nueva");
  });

  it("ignora campos no diffeables (p.ej. coach_notes)", () => {
    const changes = diffSessionValues(
      { ...base, coach_notes: "antes" },
      { ...base, coach_notes: "ahora" },
    );
    expect(changes).toEqual([]);
  });
});

describe("diffAthleteIds", () => {
  it("retorna changed=false cuando los conjuntos coinciden", () => {
    expect(diffAthleteIds([1, 2, 3], [3, 2, 1])).toEqual({
      added: [],
      removed: [],
      changed: false,
    });
  });

  it("detecta atletas añadidos", () => {
    const d = diffAthleteIds([1, 2], [1, 2, 3]);
    expect(d.added).toEqual([3]);
    expect(d.removed).toEqual([]);
    expect(d.changed).toBe(true);
  });

  it("detecta atletas removidos", () => {
    const d = diffAthleteIds([1, 2, 3], [1, 3]);
    expect(d.added).toEqual([]);
    expect(d.removed).toEqual([2]);
    expect(d.changed).toBe(true);
  });

  it("detecta added y removed al mismo tiempo", () => {
    const d = diffAthleteIds([1, 2], [2, 4]);
    expect(d.added).toEqual([4]);
    expect(d.removed).toEqual([1]);
    expect(d.changed).toBe(true);
  });
});
