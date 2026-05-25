import { describe, it, expect } from "vitest";

import {
  RACE_CALENDAR_2026,
  getRaceMeta,
  getRaceTypeBadgeStyle,
  getValidaLabel,
} from "@/lib/raceCalendar";

describe("raceCalendar — RACE_CALENDAR_2026", () => {
  it("incluye las 7 válidas + el Departamental", () => {
    expect(Object.keys(RACE_CALENDAR_2026).sort()).toEqual(
      ["1", "2", "3", "4", "5", "6", "7", "99"].sort(),
    );
  });

  it("Válida IV (Cali) es tipo A con tapering 5-7d", () => {
    expect(RACE_CALENDAR_2026[4]).toEqual({
      type: "A",
      label: "Cali",
      tapering: "5-7d",
      date_iso: "2026-05-17",
      location: "Cali",
    });
  });

  it("Válida III (La Cumbre) es tipo C diagnóstica sin tapering", () => {
    expect(RACE_CALENDAR_2026[3].type).toBe("C");
    expect(RACE_CALENDAR_2026[3].tapering).toBe("sin");
  });

  it("Departamental (99) es CD con tapering completo", () => {
    expect(RACE_CALENDAR_2026[99].type).toBe("CD");
    expect(RACE_CALENDAR_2026[99].tapering).toBe("5-7d");
  });
});

describe("raceCalendar — getRaceMeta", () => {
  it("devuelve metadata para válida conocida en 2026", () => {
    const meta = getRaceMeta(2026, 4);
    expect(meta).not.toBeNull();
    expect(meta?.type).toBe("A");
  });

  it("devuelve null para temporada distinta a 2026", () => {
    expect(getRaceMeta(2025, 4)).toBeNull();
    expect(getRaceMeta(2027, 1)).toBeNull();
  });

  it("devuelve null para válida no mapeada", () => {
    expect(getRaceMeta(2026, 999)).toBeNull();
  });

  it("devuelve null cuando validaNum es null o undefined", () => {
    expect(getRaceMeta(2026, null)).toBeNull();
    expect(getRaceMeta(2026, undefined)).toBeNull();
  });
});

describe("raceCalendar — getRaceTypeBadgeStyle", () => {
  it("tipo A usa rojo y label 'Pico'", () => {
    const style = getRaceTypeBadgeStyle("A");
    expect(style.className).toMatch(/red/);
    expect(style.label).toMatch(/Pico/);
  });

  it("tipo B usa naranja", () => {
    expect(getRaceTypeBadgeStyle("B").className).toMatch(/orange/);
  });

  it("tipo C usa azul y label 'Diagnóstica'", () => {
    const style = getRaceTypeBadgeStyle("C");
    expect(style.className).toMatch(/blue/);
    expect(style.label).toMatch(/Diagnóstica/);
  });

  it("tipo CD usa púrpura", () => {
    expect(getRaceTypeBadgeStyle("CD").className).toMatch(/purple/);
  });
});

describe("raceCalendar — getValidaLabel", () => {
  it("formatea números regulares en romanos", () => {
    expect(getValidaLabel(1)).toBe("Válida I");
    expect(getValidaLabel(4)).toBe("Válida IV");
    expect(getValidaLabel(7)).toBe("Válida VII");
  });

  it("Departamental (99) usa label dedicado", () => {
    expect(getValidaLabel(99)).toBe("Cto. Departamental");
  });

  it("null/undefined → guión", () => {
    expect(getValidaLabel(null)).toBe("—");
    expect(getValidaLabel(undefined)).toBe("—");
  });
});
