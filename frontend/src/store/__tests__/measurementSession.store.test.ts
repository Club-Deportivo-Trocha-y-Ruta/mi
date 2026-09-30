/**
 * measurementSession.store (feature 048, T044): transiciones de la cola y
 * garantía de que la jornada nunca se escribe en almacenamiento del navegador.
 * Ids sintéticos, sin datos de menores.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth.store";
import { nextPendingId, useMeasurementSessionStore } from "@/store/measurementSession.store";

const store = () => useMeasurementSessionStore.getState();

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  store().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("measurementSession.store", () => {
  it("start deja todos pendientes y el primero en captura", () => {
    store().start("2026-09-29", [1, 2, 3, 2]);
    const s = store();
    expect(s.date).toBe("2026-09-29");
    expect(s.athleteIds).toEqual([1, 2, 3]);
    expect(s.statusById).toEqual({ 1: "pending", 2: "pending", 3: "pending" });
    expect(s.currentId).toBe(1);
  });

  it("markMeasured guarda el registro y avanza al siguiente pendiente", () => {
    store().start("2026-09-29", [1, 2, 3]);
    store().markMeasured(1, 500, true);
    const s = store();
    expect(s.statusById[1]).toBe("measured");
    expect(s.recordIdById[1]).toBe(500);
    expect(s.warningsById[1]).toBe(true);
    expect(s.currentId).toBe(2);
  });

  it("skip avanza y, al no quedar pendientes, currentId es null", () => {
    store().start("2026-09-29", [1, 2]);
    store().skip(1);
    expect(store().currentId).toBe(2);
    store().markMeasured(2, 7, false);
    expect(store().currentId).toBeNull();
    expect(store().statusById).toEqual({ 1: "skipped", 2: "measured" });
  });

  it("el avance es circular: vuelve a un pendiente anterior", () => {
    store().start("2026-09-29", [1, 2, 3]);
    store().goTo(3);
    store().markMeasured(3, 9, false);
    expect(store().currentId).toBe(1);
  });

  it("reopen devuelve un omitido a pendiente y lo pone en captura", () => {
    store().start("2026-09-29", [1, 2]);
    store().skip(1);
    store().reopen(1);
    expect(store().statusById[1]).toBe("pending");
    expect(store().currentId).toBe(1);
  });

  it("reopen y skip no alteran a un medido", () => {
    store().start("2026-09-29", [1, 2]);
    store().markMeasured(1, 4, false);
    store().reopen(1);
    store().skip(1);
    expect(store().statusById[1]).toBe("measured");
  });

  it("goTo salta a un pendiente, reabre un omitido e ignora a un medido", () => {
    store().start("2026-09-29", [1, 2, 3]);
    store().goTo(3);
    expect(store().currentId).toBe(3);
    store().skip(3);
    store().goTo(3);
    expect(store().statusById[3]).toBe("pending");
    expect(store().currentId).toBe(3);
    store().markMeasured(3, 1, false);
    const before = store().currentId;
    store().goTo(3);
    expect(store().currentId).toBe(before);
  });

  it("next avanza sin cambiar estados", () => {
    store().start("2026-09-29", [1, 2]);
    store().next();
    expect(store().currentId).toBe(2);
    expect(store().statusById).toEqual({ 1: "pending", 2: "pending" });
  });

  it("reset vuelve al estado inicial", () => {
    store().start("2026-09-29", [1]);
    store().reset();
    expect(store().date).toBeNull();
    expect(store().athleteIds).toEqual([]);
    expect(store().currentId).toBeNull();
  });

  it("nextPendingId devuelve null en una cola vacía", () => {
    expect(nextPendingId([], {}, null)).toBeNull();
  });

  it("no escribe nada en localStorage ni sessionStorage", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    store().start("2026-09-29", [1, 2, 3]);
    store().markMeasured(1, 500, true);
    store().skip(2);
    store().reopen(2);
    store().next();
    store().reset();
    expect(setItem).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("logout() del auth store limpia la jornada", () => {
    store().start("2026-09-29", [1, 2]);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    useAuthStore.getState().logout();
    expect(store().date).toBeNull();
    expect(store().athleteIds).toEqual([]);
  });
});
