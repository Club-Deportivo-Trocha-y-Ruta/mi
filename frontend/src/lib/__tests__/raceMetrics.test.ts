import { describe, it, expect } from "vitest";

import {
  computeBestTimeForSeason,
  evaluateImprovementCount,
  formatDeltaRank,
  formatDeltaTime,
  formatQualitativePodiumProximity,
  formatQualitativeRank,
  formatRaceTime,
} from "@/lib/raceMetrics";

describe("raceMetrics — formatRaceTime", () => {
  it("formatea m:ss.s para tiempos bajo 1 hora", () => {
    // 42 min 18.4 s = 2_538_400 ms
    expect(formatRaceTime(2_538_400)).toBe("42:18.4");
  });

  it("formatea h:mm:ss.s para tiempos ≥ 1 hora", () => {
    expect(formatRaceTime(3_600_000)).toBe("1:00:00.0");
    // 1h 5m 8.3s = 3_908_300 ms
    expect(formatRaceTime(3_908_300)).toBe("1:05:08.3");
  });

  it("formatea menos de 1 minuto con 0 minutos al inicio", () => {
    expect(formatRaceTime(45_200)).toBe("0:45.2");
  });

  it("padding de segundos < 10", () => {
    // 5 min 8.3 s
    expect(formatRaceTime(308_300)).toBe("5:08.3");
  });

  it("null y undefined devuelven guión largo", () => {
    expect(formatRaceTime(null)).toBe("—");
    expect(formatRaceTime(undefined)).toBe("—");
  });

  it("NaN devuelve guión largo", () => {
    expect(formatRaceTime(Number.NaN)).toBe("—");
  });
});

describe("raceMetrics — formatDeltaTime", () => {
  it("delta negativo bajo 1 minuto usa sufijo s", () => {
    expect(formatDeltaTime(-45_200)).toBe("−45.2s");
  });

  it("delta positivo bajo 1 minuto usa sufijo s", () => {
    expect(formatDeltaTime(12_000)).toBe("+12.0s");
  });

  it("delta negativo > 1 minuto formato −m:ss.s", () => {
    expect(formatDeltaTime(-85_700)).toBe("−1:25.7");
  });

  it("delta positivo > 1 minuto formato +m:ss.s", () => {
    expect(formatDeltaTime(127_500)).toBe("+2:07.5");
  });

  it("cero devuelve 0.0s explícito", () => {
    expect(formatDeltaTime(0)).toBe("0.0s");
  });

  it("usa el carácter unicode − (U+2212) para negativos", () => {
    const result = formatDeltaTime(-45_000);
    expect(result.charCodeAt(0)).toBe(0x2212);
  });

  it("null devuelve guión largo", () => {
    expect(formatDeltaTime(null)).toBe("—");
    expect(formatDeltaTime(undefined)).toBe("—");
  });
});

describe("raceMetrics — formatDeltaRank", () => {
  it("delta negativo: mejoró", () => {
    expect(formatDeltaRank(-3)).toBe("−3 puestos");
    expect(formatDeltaRank(-1)).toBe("−1 puesto");
  });

  it("delta positivo: bajó", () => {
    expect(formatDeltaRank(2)).toBe("+2 puestos");
    expect(formatDeltaRank(1)).toBe("+1 puesto");
  });

  it("delta 0 → 'Mantuvo'", () => {
    expect(formatDeltaRank(0)).toBe("Mantuvo");
  });

  it("null/undef → guión", () => {
    expect(formatDeltaRank(null)).toBe("—");
    expect(formatDeltaRank(undefined)).toBe("—");
  });
});

describe("raceMetrics — computeBestTimeForSeason", () => {
  it("retorna el mínimo entre snapshots V1 con race_time_ms numérico", () => {
    const best = computeBestTimeForSeason([
      { metrics_snapshot: { schema_version: 1, race_time_ms: 2_500_000 } },
      { metrics_snapshot: { schema_version: 1, race_time_ms: 2_400_000 } },
      { metrics_snapshot: { schema_version: 1, race_time_ms: 2_600_000 } },
    ]);
    expect(best).toBe(2_400_000);
  });

  it("ignora snapshots sin schema_version V1", () => {
    const best = computeBestTimeForSeason([
      { metrics_snapshot: { schema_version: 1, race_time_ms: 2_500_000 } },
      // Snapshot legacy: no debe contar.
      { metrics_snapshot: { race_time_ms: 1_000_000 } },
    ]);
    expect(best).toBe(2_500_000);
  });

  it("ignora snapshots con race_time_ms null", () => {
    const best = computeBestTimeForSeason([
      { metrics_snapshot: { schema_version: 1, race_time_ms: null } },
      { metrics_snapshot: { schema_version: 1, race_time_ms: 2_500_000 } },
    ]);
    expect(best).toBe(2_500_000);
  });

  it("retorna null cuando la lista está vacía", () => {
    expect(computeBestTimeForSeason([])).toBeNull();
  });

  it("retorna null cuando no hay snapshots utilizables", () => {
    expect(
      computeBestTimeForSeason([
        { metrics_snapshot: { race_time_ms: 2_500_000 } }, // sin schema_version
        { metrics_snapshot: { schema_version: 1, race_time_ms: null } },
        { metrics_snapshot: null },
      ]),
    ).toBeNull();
  });
});

describe("raceMetrics — evaluateImprovementCount", () => {
  it("2 deltas negativos → 2 mejoras", () => {
    expect(
      evaluateImprovementCount({
        rank: -3,
        gap: -75_000,
      }),
    ).toEqual({ improved: 2, total: 2 });
  });

  it("uno mejora, uno empeora", () => {
    expect(
      evaluateImprovementCount({
        rank: -1, // mejoró
        gap: 5_000, // empeoró
      }),
    ).toEqual({ improved: 1, total: 2 });
  });

  it("delta 0 NO cuenta como mejora", () => {
    expect(
      evaluateImprovementCount({
        rank: 0,
        gap: 0,
      }),
    ).toEqual({ improved: 0, total: 2 });
  });

  it("null no se cuenta en el total", () => {
    expect(
      evaluateImprovementCount({
        rank: -2,
        gap: null,
      }),
    ).toEqual({ improved: 1, total: 1 });
  });
});

describe("raceMetrics — formatQualitativeRank (vista parent)", () => {
  it("delta negativo: 'Mejoró N puesto(s)'", () => {
    expect(formatQualitativeRank(-1)).toBe("Mejoró 1 puesto");
    expect(formatQualitativeRank(-4)).toBe("Mejoró 4 puestos");
  });

  it("delta positivo: 'Bajó N puesto(s)'", () => {
    expect(formatQualitativeRank(1)).toBe("Bajó 1 puesto");
    expect(formatQualitativeRank(3)).toBe("Bajó 3 puestos");
  });

  it("delta 0: 'Mantuvo posición'", () => {
    expect(formatQualitativeRank(0)).toBe("Mantuvo posición");
  });

  it("null: 'Sin datos para comparar'", () => {
    expect(formatQualitativeRank(null)).toBe("Sin datos para comparar");
    expect(formatQualitativeRank(undefined)).toBe("Sin datos para comparar");
  });
});

describe("raceMetrics — formatQualitativePodiumProximity (vista parent)", () => {
  it("≤30s → 'Muy cerca del podio'", () => {
    expect(formatQualitativePodiumProximity(20_000)).toBe("Muy cerca del podio");
    expect(formatQualitativePodiumProximity(30_000)).toBe("Muy cerca del podio");
  });

  it("≤90s → 'Cerca del podio'", () => {
    expect(formatQualitativePodiumProximity(45_000)).toBe("Cerca del podio");
    expect(formatQualitativePodiumProximity(90_000)).toBe("Cerca del podio");
  });

  it("≤180s → 'En desarrollo'", () => {
    expect(formatQualitativePodiumProximity(120_000)).toBe("En desarrollo");
    expect(formatQualitativePodiumProximity(180_000)).toBe("En desarrollo");
  });

  it(">180s → 'Construyendo base'", () => {
    expect(formatQualitativePodiumProximity(300_000)).toBe("Construyendo base");
  });

  it("null/undef → 'Sin datos'", () => {
    expect(formatQualitativePodiumProximity(null)).toBe("Sin datos");
  });
});
