/**
 * Tests — useFormDraft expiry and cross-account cleanup (feature 046 T081).
 *
 * Covers privacy-audit F8: a capture draft ("skinfolds:{recordId}" target,
 * but the rule is generic to every `useFormDraft` consumer) must not be
 * offered for restore once it is older than 24 h ("within the same day",
 * spec US1 #7 / FR-008), and `clearAllDrafts()` — called from
 * `auth.store.ts` on logout — must wipe every draft key regardless of user
 * or target so a shared tablet never restores the previous account's
 * half-finished set.
 *
 * Data: synthetic ids only, no name or measurement of a real minor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { clearAllDrafts, useFormDraft, type FormDraft } from "@/hooks/useFormDraft";

const USER_ID = 42;
const RECORD_ID = 812;
const TARGET = `skinfolds:${RECORD_ID}`;
const KEY = `tyr:session-draft:v1:${USER_ID}:${TARGET}`;

function writeDraft(overrides: Partial<FormDraft<{ note: string }>> = {}) {
  const draft: FormDraft<{ note: string }> = {
    version: "v1",
    values: { note: "borrador" },
    step: 1,
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
  window.localStorage.setItem(KEY, JSON.stringify(draft));
  return draft;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.useRealTimers();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("useFormDraft — expiración a 24 h", () => {
  it("ofrece restaurar un borrador reciente", () => {
    writeDraft();
    const { result } = renderHook(() =>
      useFormDraft<{ note: string }>({ userId: USER_ID, target: TARGET }),
    );
    expect(result.current.restoreCandidate).not.toBeNull();
  });

  it("descarta un borrador de más de 24 h y no lo ofrece", () => {
    const stale = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString();
    writeDraft({ updatedAt: stale });
    const { result } = renderHook(() =>
      useFormDraft<{ note: string }>({ userId: USER_ID, target: TARGET }),
    );
    expect(result.current.restoreCandidate).toBeNull();
  });

  it("borra la clave del borrador expirado en localStorage al leerlo", () => {
    const stale = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
    writeDraft({ updatedAt: stale });
    renderHook(() => useFormDraft<{ note: string }>({ userId: USER_ID, target: TARGET }));
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("un borrador de justo 23:59 sigue ofreciéndose (dentro del mismo día)", () => {
    const almostADay = new Date(Date.now() - (24 * 60 * 60 * 1000 - 60_000)).toISOString();
    writeDraft({ updatedAt: almostADay });
    const { result } = renderHook(() =>
      useFormDraft<{ note: string }>({ userId: USER_ID, target: TARGET }),
    );
    expect(result.current.restoreCandidate).not.toBeNull();
  });
});

describe("useFormDraft — flush síncrono en pagehide/beforeunload", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("persiste un guardado debounced todavía pendiente cuando la pestaña se recarga antes del timeout", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useFormDraft<{ note: string }>({ userId: USER_ID, target: TARGET, debounceMs: 800 }),
    );

    result.current.saveDraft({ note: "a mitad de captura" }, 3);
    // Antes de que venzan los 800 ms del debounce: nada persistido todavía.
    expect(window.localStorage.getItem(KEY)).toBeNull();

    // Recarga (`page.reload()` en Playwright dispara `pagehide`): el
    // guardado pendiente debe volcarse a localStorage de inmediato, sin
    // esperar el debounce — si no, el borrador se pierde justo en el
    // escenario ("recarga a mitad de captura") que esta función existe
    // para cubrir (frontend/e2e/body-composition.spec.ts).
    window.dispatchEvent(new Event("pagehide"));

    const saved = window.localStorage.getItem(KEY);
    expect(saved).not.toBeNull();
    const parsed = JSON.parse(saved as string) as FormDraft<{ note: string }>;
    expect(parsed.values).toEqual({ note: "a mitad de captura" });
    expect(parsed.step).toBe(3);
  });

  it("no revienta ni escribe nada si no hay guardado pendiente al recargar", () => {
    vi.useFakeTimers();
    renderHook(() =>
      useFormDraft<{ note: string }>({ userId: USER_ID, target: TARGET, debounceMs: 800 }),
    );

    expect(() => window.dispatchEvent(new Event("pagehide"))).not.toThrow();
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });
});

describe("clearAllDrafts", () => {
  it("borra borradores de distintos usuarios y destinos", () => {
    writeDraft();
    window.localStorage.setItem(
      "tyr:session-draft:v1:99:new",
      JSON.stringify({ version: "v1", values: {}, step: 0, updatedAt: new Date().toISOString() }),
    );
    window.localStorage.setItem("unrelated:key", "no debe tocarse");

    clearAllDrafts();

    expect(window.localStorage.getItem(KEY)).toBeNull();
    expect(window.localStorage.getItem("tyr:session-draft:v1:99:new")).toBeNull();
    expect(window.localStorage.getItem("unrelated:key")).toBe("no debe tocarse");
  });

  it("no revienta cuando no hay ningún borrador guardado", () => {
    expect(() => clearAllDrafts()).not.toThrow();
  });
});
