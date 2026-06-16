/**
 * Tests unitarios para raceOptionLabel.ts (feature 016).
 *
 * Módulo puro: sin React, sin I/O, sin efectos secundarios.
 * Cubre cada rama de todas las funciones exportadas — base para
 * la validación de mutaciones en T029.
 */
import { describe, expect, it } from "vitest";

import {
  SEASON_AGGREGATE,
  aggregateLabel,
  isAggregateOption,
  parseEventId,
  raceOptionValue,
} from "./raceOptionLabel";

// ---------------------------------------------------------------------------
// SEASON_AGGREGATE — invariantes del sentinel
// ---------------------------------------------------------------------------

describe("SEASON_AGGREGATE", () => {
  it("no es igual a ningún entero positivo serializado", () => {
    expect(SEASON_AGGREGATE).not.toBe("1");
    expect(SEASON_AGGREGATE).not.toBe("21");
    expect(SEASON_AGGREGATE).not.toBe("100");
  });

  it("no es igual a 0 ni a enteros negativos", () => {
    expect(SEASON_AGGREGATE).not.toBe("0");
    expect(SEASON_AGGREGATE).not.toBe("-1");
  });

  it("no es NaN ni undefined", () => {
    expect(SEASON_AGGREGATE).not.toBe("NaN");
    expect(SEASON_AGGREGATE).not.toBeUndefined();
  });

  it("Number(SEASON_AGGREGATE) es NaN — garantiza no-colisión con ids numéricos", () => {
    expect(Number(SEASON_AGGREGATE)).toBeNaN();
  });
});

// ---------------------------------------------------------------------------
// raceOptionValue — serialización de event_id
// ---------------------------------------------------------------------------

describe("raceOptionValue", () => {
  it("convierte event_id 21 al string '21'", () => {
    expect(raceOptionValue(21)).toBe("21");
  });

  it("convierte event_id 1 al string '1'", () => {
    expect(raceOptionValue(1)).toBe("1");
  });

  it("round-trip: parseEventId(raceOptionValue(n)) === n", () => {
    expect(parseEventId(raceOptionValue(21))).toBe(21);
    expect(parseEventId(raceOptionValue(1))).toBe(1);
    expect(parseEventId(raceOptionValue(100))).toBe(100);
  });

  it("nunca produce un valor igual a SEASON_AGGREGATE", () => {
    // event_id positivos nunca deben colidir con el sentinel
    for (const id of [1, 2, 7, 21, 99]) {
      expect(raceOptionValue(id)).not.toBe(SEASON_AGGREGATE);
    }
  });
});

// ---------------------------------------------------------------------------
// isAggregateOption — guard de tipo
// ---------------------------------------------------------------------------

describe("isAggregateOption", () => {
  it("devuelve true cuando el valor es SEASON_AGGREGATE", () => {
    expect(isAggregateOption(SEASON_AGGREGATE)).toBe(true);
  });

  it("devuelve false para un event_id serializado '21'", () => {
    expect(isAggregateOption(raceOptionValue(21))).toBe(false);
  });

  it("devuelve false para el string '1'", () => {
    expect(isAggregateOption("1")).toBe(false);
  });

  it("devuelve false para cualquier string de id positivo", () => {
    for (const id of [1, 3, 7, 42]) {
      expect(isAggregateOption(raceOptionValue(id))).toBe(false);
    }
  });

  it("devuelve false para string vacío (no es el sentinel)", () => {
    expect(isAggregateOption("")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// aggregateLabel — etiqueta en español
// ---------------------------------------------------------------------------

describe("aggregateLabel", () => {
  it("devuelve exactamente 'Temporada (todas)'", () => {
    expect(aggregateLabel()).toBe("Temporada (todas)");
  });

  it("es idempotente — llamadas sucesivas devuelven el mismo valor", () => {
    expect(aggregateLabel()).toBe(aggregateLabel());
  });
});

// ---------------------------------------------------------------------------
// parseEventId — deserialización y ramas
// ---------------------------------------------------------------------------

describe("parseEventId", () => {
  it("devuelve null para SEASON_AGGREGATE (rama aggregate)", () => {
    expect(parseEventId(SEASON_AGGREGATE)).toBeNull();
  });

  it("devuelve el número para un id serializado (rama race id)", () => {
    expect(parseEventId("21")).toBe(21);
    expect(parseEventId("1")).toBe(1);
  });

  it("round-trip: raceOptionValue(parseEventId(raceOptionValue(n))!) === raceOptionValue(n)", () => {
    const val = raceOptionValue(7);
    const parsed = parseEventId(val);
    expect(parsed).not.toBeNull();
    expect(raceOptionValue(parsed!)).toBe(val);
  });
});
