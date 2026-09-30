/**
 * Preferencias del dispositivo para la captura antropométrica (feature 048, R8).
 * No son datos personales; no se limpian al cerrar sesión.
 */

export type CaptureMode = "guided" | "quick";

export const CAPTURE_MODE_KEY = "tyr.anthro.captureMode";
export const BENCH_HEIGHT_KEY = "tyr.anthro.benchHeightCm";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // localStorage bloqueado o lleno: la preferencia simplemente no persiste.
  }
}

export function getCaptureMode(): CaptureMode {
  return read(CAPTURE_MODE_KEY) === "quick" ? "quick" : "guided";
}

export function setCaptureMode(mode: CaptureMode): void {
  write(CAPTURE_MODE_KEY, mode);
}

export function getBenchHeightCm(): number | null {
  const raw = read(BENCH_HEIGHT_KEY);
  if (raw === null || raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

export function setBenchHeightCm(value: number | null): void {
  if (value === null || !Number.isFinite(value) || value < 0) {
    write(BENCH_HEIGHT_KEY, null);
    return;
  }
  write(BENCH_HEIGHT_KEY, String(value));
}
