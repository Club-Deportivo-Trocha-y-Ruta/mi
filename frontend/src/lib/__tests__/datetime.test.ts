import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  formatDate,
  formatDateMedium,
  formatDateShort,
  formatDateTime,
  formatDateTimeCompact,
  formatDayMonth,
  formatDayMonthShort,
  formatFullDate,
  formatRelativeDay,
  formatTime,
  formatWeekdayShortDate,
} from "@/lib/datetime";

// 2026-05-25T23:13:00Z = 2026-05-25 18:13 en UTC-5 (America/Bogota).
// Usamos este valor para verificar que la TZ del runner no afecta el output.
// es-CO usa formato 12h: 18:13 se muestra como "06:13 p. m." — el helper
// formatDateTimeCompact usa hour12:false para verificar "18:13" explícito.
const UTC_23_13 = "2026-05-25T23:13:00Z";
const DATE_ONLY = "2026-05-25";

describe("formatDateTime", () => {
  it("aplica TZ Colombia (UTC-5) para un timestamp UTC", () => {
    // 23:13 UTC → 18:13 en Bogotá. es-CO usa 12h: "06:13 p. m."
    // Verificamos día correcto (25, no se desplaza al 26) y hora 12h de Colombia.
    const result = formatDateTime(UTC_23_13);
    expect(result).toContain("25");
    expect(result).toContain("mayo");
    expect(result).toContain("2026");
    // 18:13 en 12h es-CO → "06:13 p. m." (el separador puede variar)
    expect(result).toMatch(/06:13/);
    expect(result.toLowerCase()).toMatch(/p\.\s*m\./);
  });

  it("devuelve string vacío para null", () => {
    expect(formatDateTime(null)).toBe("");
  });

  it("devuelve string vacío para undefined", () => {
    expect(formatDateTime(undefined)).toBe("");
  });

  it("devuelve string vacío para string vacío", () => {
    expect(formatDateTime("")).toBe("");
  });

  it("devuelve string vacío para fecha inválida", () => {
    expect(formatDateTime("no-es-fecha")).toBe("");
  });

  it("acepta un objeto Date", () => {
    const d = new Date(UTC_23_13);
    const result = formatDateTime(d);
    // 18:13 en 12h es-CO → "06:13 p. m."
    expect(result).toMatch(/06:13/);
  });
});

describe("formatDate", () => {
  it("formatea fecha completa en español Colombia", () => {
    const result = formatDate(UTC_23_13);
    expect(result).toMatch(/25 de mayo de 2026/);
  });

  it("devuelve string vacío para null", () => {
    expect(formatDate(null)).toBe("");
  });

  it("acepta string solo-fecha con noon ficticio para evitar TZ-shift", () => {
    // "2026-05-25" como string ISO sin hora se interpreta en UTC,
    // lo que podría desplazar el día en TZ Colombia (-5).
    // Verificamos que el módulo lo maneja (puede mostrar 24 si el input es medianoche UTC).
    // El comportamiento correcto: el llamador debe pasar T12:00:00 si quiere día estable.
    // Para fechas-only recomendamos formatear con el truco T12 en el call site;
    // aquí solo verificamos que no explota.
    const result = formatDate(DATE_ONLY);
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  });
});

describe("formatTime", () => {
  it("devuelve la hora en Colombia para timestamp UTC", () => {
    // 23:13 UTC → 18:13 en Bogotá. es-CO usa 12h: "06:13 p. m."
    const result = formatTime(UTC_23_13);
    expect(result).toMatch(/06:13/);
    expect(result.toLowerCase()).toMatch(/p\.\s*m\./);
  });

  it("devuelve string vacío para null", () => {
    expect(formatTime(null)).toBe("");
  });
});

describe("formatDateShort", () => {
  it("formatea como DD/MM/YYYY en Colombia", () => {
    const result = formatDateShort(UTC_23_13);
    expect(result).toBe("25/05/2026");
  });

  it("devuelve string vacío para undefined", () => {
    expect(formatDateShort(undefined)).toBe("");
  });
});

describe("formatDayMonth", () => {
  it("omite el año y muestra día y mes completo", () => {
    const result = formatDayMonth(UTC_23_13);
    expect(result).toMatch(/25 de mayo/);
    expect(result).not.toContain("2026");
  });

  it("devuelve string vacío para null", () => {
    expect(formatDayMonth(null)).toBe("");
  });
});

describe("formatDateMedium", () => {
  it("formatea como día + mes abreviado + año", () => {
    const result = formatDateMedium(UTC_23_13);
    expect(result).toContain("25");
    expect(result).toContain("2026");
    // mes abreviado en es-CO
    expect(result.toLowerCase()).toMatch(/may/);
  });

  it("devuelve string vacío para string vacío", () => {
    expect(formatDateMedium("")).toBe("");
  });
});

describe("formatDayMonthShort", () => {
  it("formatea como día + mes abreviado sin año", () => {
    const result = formatDayMonthShort(UTC_23_13);
    expect(result).toContain("25");
    expect(result.toLowerCase()).toMatch(/may/);
    expect(result).not.toContain("2026");
  });
});

describe("formatFullDate", () => {
  it("incluye día de la semana largo, día, mes y año", () => {
    const result = formatFullDate(UTC_23_13);
    // lunes, 25 de mayo de 2026
    expect(result).toMatch(/lunes/i);
    expect(result).toContain("25");
    expect(result).toContain("mayo");
    expect(result).toContain("2026");
  });

  it("devuelve string vacío para null", () => {
    expect(formatFullDate(null)).toBe("");
  });
});

describe("formatWeekdayShortDate", () => {
  it("incluye weekday corto, día y mes abreviado", () => {
    const result = formatWeekdayShortDate(UTC_23_13);
    // lun., 25 may. (formato varía levemente por plataforma, pero debe incluir lun)
    expect(result.toLowerCase()).toMatch(/lun/);
    expect(result).toContain("25");
    expect(result.toLowerCase()).toMatch(/may/);
  });
});

describe("formatDateTimeCompact", () => {
  it("combina fecha corta con hora 24h separada por ·, en TZ Colombia", () => {
    // 23:13 UTC → 18:13 en Bogotá
    const result = formatDateTimeCompact(UTC_23_13);
    expect(result).toContain("·");
    expect(result).toContain("18:13");
    expect(result).toContain("2026");
    expect(result.toLowerCase()).toMatch(/may/);
  });

  it("devuelve string vacío para null", () => {
    expect(formatDateTimeCompact(null)).toBe("");
  });
});

describe("formatRelativeDay", () => {
  beforeEach(() => {
    // Fijamos "hoy" al 2026-05-25 12:00 en UTC (= 07:00 en Bogotá, mismo día)
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-25T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('devuelve "Hoy" para un timestamp del mismo día en Colombia', () => {
    // 2026-05-25T20:00:00Z = 2026-05-25 15:00 en Bogotá
    expect(formatRelativeDay("2026-05-25T20:00:00Z")).toBe("Hoy");
  });

  it('devuelve "Ayer" para un timestamp del día anterior en Colombia', () => {
    expect(formatRelativeDay("2026-05-24T20:00:00Z")).toBe("Ayer");
  });

  it('devuelve "Mañana" para un timestamp del día siguiente en Colombia', () => {
    expect(formatRelativeDay("2026-05-26T20:00:00Z")).toBe("Mañana");
  });

  it("devuelve fecha completa formateada para días más distantes", () => {
    const result = formatRelativeDay("2026-05-20T20:00:00Z");
    expect(result).toMatch(/20 de mayo de 2026/);
  });

  it("devuelve string vacío para null", () => {
    expect(formatRelativeDay(null)).toBe("");
  });

  it("devuelve string vacío para string vacío", () => {
    expect(formatRelativeDay("")).toBe("");
  });
});
