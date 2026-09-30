import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BENCH_HEIGHT_KEY,
  CAPTURE_MODE_KEY,
  getBenchHeightCm,
  getCaptureMode,
  setBenchHeightCm,
  setCaptureMode,
} from "./devicePrefs";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("captureMode", () => {
  it("por defecto es guided", () => {
    expect(getCaptureMode()).toBe("guided");
  });
  it("persiste quick y guided", () => {
    setCaptureMode("quick");
    expect(getCaptureMode()).toBe("quick");
    setCaptureMode("guided");
    expect(getCaptureMode()).toBe("guided");
  });
  it("valor inválido cae a guided", () => {
    window.localStorage.setItem(CAPTURE_MODE_KEY, "otro");
    expect(getCaptureMode()).toBe("guided");
  });
});

describe("benchHeightCm", () => {
  it("por defecto es null", () => {
    expect(getBenchHeightCm()).toBeNull();
  });
  it("guarda y lee un número", () => {
    setBenchHeightCm(45.5);
    expect(getBenchHeightCm()).toBe(45.5);
  });
  it("null borra la preferencia", () => {
    setBenchHeightCm(40);
    setBenchHeightCm(null);
    expect(window.localStorage.getItem(BENCH_HEIGHT_KEY)).toBeNull();
    expect(getBenchHeightCm()).toBeNull();
  });
  it("ignora valores corruptos o negativos", () => {
    window.localStorage.setItem(BENCH_HEIGHT_KEY, "abc");
    expect(getBenchHeightCm()).toBeNull();
    window.localStorage.setItem(BENCH_HEIGHT_KEY, "-3");
    expect(getBenchHeightCm()).toBeNull();
  });
});

describe("localStorage no disponible", () => {
  it("no lanza y devuelve los defaults", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(getCaptureMode()).toBe("guided");
    expect(getBenchHeightCm()).toBeNull();
    expect(() => setCaptureMode("quick")).not.toThrow();
    expect(() => setBenchHeightCm(40)).not.toThrow();
  });
});
