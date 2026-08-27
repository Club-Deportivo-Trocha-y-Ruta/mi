/**
 * Tests de `useSidebarCollapsed` (feature 035).
 *
 * Cubre:
 *  - Default sin valor almacenado: riel sólo dentro del rango tablet
 *    (768–1023px) según `matchMedia`.
 *  - La preferencia persistida gana siempre sobre el default de viewport.
 *  - `toggle` invierte el estado y lo persiste bajo `tyr:nav-collapsed:v1`.
 *  - Degradación sin `matchMedia` (jsdom puro) y con `localStorage` que lanza.
 *  - Control manual: tras el montaje el hook no reacciona al viewport.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import {
  SIDEBAR_COLLAPSED_STORAGE_KEY,
  useSidebarCollapsed,
} from "@/hooks/layout/useSidebarCollapsed";

// jsdom no implementa matchMedia: cada test instala el suyo (o ninguno, para
// probar la guarda).
const originalMatchMedia = window.matchMedia;

interface FakeMql {
  matches: boolean;
  media: string;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
  addListener: ReturnType<typeof vi.fn>;
  removeListener: ReturnType<typeof vi.fn>;
  onchange: null;
  dispatchEvent: ReturnType<typeof vi.fn>;
}

function installMatchMedia(matches: boolean): FakeMql {
  const mql: FakeMql = {
    matches,
    media: "",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  };
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn((query: string) => {
      mql.media = query;
      return mql;
    }),
  });
  return mql;
}

function removeMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: undefined,
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: originalMatchMedia,
  });
  vi.restoreAllMocks();
});

describe("useSidebarCollapsed — default sin preferencia almacenada", () => {
  it("en el rango tablet (matchMedia coincide) arranca en riel", () => {
    const mql = installMatchMedia(true);

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(true);
    expect(mql.media).toBe("(min-width: 768px) and (max-width: 1023px)");
  });

  it("fuera del rango tablet arranca expandida", () => {
    installMatchMedia(false);

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(false);
  });

  it("sin matchMedia disponible (jsdom/SSR) degrada a expandida sin lanzar", () => {
    removeMatchMedia();

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(false);
  });

  it("no persiste nada mientras el usuario no elija", () => {
    installMatchMedia(true);

    renderHook(() => useSidebarCollapsed());

    expect(
      window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY),
    ).toBeNull();
  });
});

describe("useSidebarCollapsed — preferencia persistida", () => {
  it("'true' almacenado gana sobre un viewport de escritorio", () => {
    installMatchMedia(false);
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "true");

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(true);
  });

  it("'false' almacenado gana sobre el default de tablet", () => {
    installMatchMedia(true);
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "false");

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(false);
  });

  it("un valor corrupto se ignora y se usa el default de viewport", () => {
    installMatchMedia(true);
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "quizás");

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(true);
  });

  it("un localStorage que lanza al leer no rompe el hook", () => {
    installMatchMedia(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(false);
  });
});

describe("useSidebarCollapsed — toggle", () => {
  it("invierte el estado y lo persiste bajo tyr:nav-collapsed:v1", () => {
    installMatchMedia(false);

    const { result } = renderHook(() => useSidebarCollapsed());

    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(true);
    expect(window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe(
      "true",
    );

    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(false);
    expect(window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe(
      "false",
    );
  });

  it("un localStorage que lanza al escribir no impide plegar la barra en memoria", () => {
    installMatchMedia(false);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });

    const { result } = renderHook(() => useSidebarCollapsed());

    act(() => result.current.toggle());

    expect(result.current.collapsed).toBe(true);
  });

  it("la elección sobrevive a un remount (se relee del storage)", () => {
    installMatchMedia(false);

    const first = renderHook(() => useSidebarCollapsed());
    act(() => first.result.current.toggle());
    first.unmount();

    const { result } = renderHook(() => useSidebarCollapsed());
    expect(result.current.collapsed).toBe(true);
  });
});

describe("useSidebarCollapsed — control manual (no reacciona al viewport)", () => {
  it("no suscribe listeners al media query", () => {
    const mql = installMatchMedia(true);

    renderHook(() => useSidebarCollapsed());

    expect(mql.addEventListener).not.toHaveBeenCalled();
    expect(mql.addListener).not.toHaveBeenCalled();
  });

  it("un cambio de viewport posterior al montaje no re-pliega la barra", () => {
    const mql = installMatchMedia(false);

    const { result, rerender } = renderHook(() => useSidebarCollapsed());
    expect(result.current.collapsed).toBe(false);

    // El dispositivo entra al rango tablet después del montaje.
    mql.matches = true;
    window.dispatchEvent(new Event("resize"));
    rerender();

    expect(result.current.collapsed).toBe(false);
  });
});
