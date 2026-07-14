/**
 * Tests vitest para useKeyboardShortcuts (feature 033, US5, T062/T064).
 *
 * Cubre:
 *  - Guardrails: sin efecto con foco en <input>/<textarea>/[contenteditable],
 *    ni con un overlay Radix abierto (`[data-state="open"]` en el DOM).
 *  - Cada binding de área: `g` luego `i/e/c/a/f/b` navega al target por
 *    defecto de la NavArea correspondiente (home/training/competitions/
 *    athletes/families/library), respetando visibilidad por rol (admin no
 *    ve "athletes").
 *  - El chord expira si la segunda tecla no llega a tiempo o no es válida.
 *  - `n` invoca onOpenQuickCreate; `?` invoca onOpenShortcutsHelp.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { useKeyboardShortcuts } from "@/hooks/layout/useKeyboardShortcuts";

function wrapper({ children }: { children: ReactNode }) {
  return createElement(MemoryRouter, null, children);
}

function press(key: string, target?: EventTarget, extra: KeyboardEventInit = {}) {
  // Default to the currently focused element, like a real browser would —
  // window.addEventListener("keydown") still receives it via bubbling, but
  // event.target must be the focused node for the typing-target guardrail.
  const dispatchTarget = target ?? document.activeElement ?? window;
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...extra });
  dispatchTarget.dispatchEvent(event);
}

function pressChord(key: string) {
  press("g");
  press(key);
}

describe("useKeyboardShortcuts", () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    document.body.innerHTML = "";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("navigates to /dashboard on g i (home / Inicio)", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("i");
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
  });

  it("navigates to /calendar on g e (training / Entrenamiento)", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("e");
    expect(mockNavigate).toHaveBeenCalledWith("/calendar");
  });

  it("navigates to /competitions on g c (Competencias)", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("c");
    expect(mockNavigate).toHaveBeenCalledWith("/competitions");
  });

  it("navigates to /athletes on g a (Atletas) for coach", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("a");
    expect(mockNavigate).toHaveBeenCalledWith("/athletes");
  });

  it("does not navigate on g a for admin (Atletas is coach-only)", () => {
    renderHook(() => useKeyboardShortcuts({ role: "admin" }), { wrapper });
    pressChord("a");
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("navigates to /parents on g f (Familias)", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("f");
    expect(mockNavigate).toHaveBeenCalledWith("/parents");
  });

  it("navigates to /technique on g b (Biblioteca)", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("b");
    expect(mockNavigate).toHaveBeenCalledWith("/technique");
  });

  it("resets the chord if the second key is not a bound area key", () => {
    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    press("g");
    press("z");
    press("i");
    // The lone "i" after an aborted chord must not navigate.
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("expires the chord after the timeout window", () => {
    vi.useFakeTimers();
    try {
      renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
      press("g");
      vi.advanceTimersByTime(2000);
      press("i");
      expect(mockNavigate).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("invokes onOpenQuickCreate on n", () => {
    const onOpenQuickCreate = vi.fn();
    renderHook(() => useKeyboardShortcuts({ role: "coach", onOpenQuickCreate }), {
      wrapper,
    });
    press("n");
    expect(onOpenQuickCreate).toHaveBeenCalledTimes(1);
  });

  it("invokes onOpenShortcutsHelp on ?", () => {
    const onOpenShortcutsHelp = vi.fn();
    renderHook(() => useKeyboardShortcuts({ role: "coach", onOpenShortcutsHelp }), {
      wrapper,
    });
    press("?");
    expect(onOpenShortcutsHelp).toHaveBeenCalledTimes(1);
  });

  it("does nothing while focus is inside an <input>", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    const onOpenQuickCreate = vi.fn();
    renderHook(() => useKeyboardShortcuts({ role: "coach", onOpenQuickCreate }), {
      wrapper,
    });

    press("n", input);
    pressChord("i");
    expect(onOpenQuickCreate).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("does nothing while focus is inside a <textarea>", () => {
    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);
    textarea.focus();

    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("e");
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("does nothing while focus is inside a contenteditable element", () => {
    const editable = document.createElement("div");
    // jsdom doesn't implement the `contentEditable` IDL setter/`isContentEditable`
    // getter, so set the attribute directly (the hook's guardrail checks both).
    editable.setAttribute("contenteditable", "true");
    editable.tabIndex = 0; // jsdom only tracks activeElement for focusable elements
    document.body.appendChild(editable);
    editable.focus();

    renderHook(() => useKeyboardShortcuts({ role: "coach" }), { wrapper });
    pressChord("c");
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("does nothing while a Radix dialog/sheet/menu is open ([data-state=open] in the DOM)", () => {
    const overlay = document.createElement("div");
    overlay.setAttribute("data-state", "open");
    document.body.appendChild(overlay);

    const onOpenQuickCreate = vi.fn();
    const onOpenShortcutsHelp = vi.fn();
    renderHook(
      () => useKeyboardShortcuts({ role: "coach", onOpenQuickCreate, onOpenShortcutsHelp }),
      { wrapper },
    );

    pressChord("i");
    press("n");
    press("?");

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(onOpenQuickCreate).not.toHaveBeenCalled();
    expect(onOpenShortcutsHelp).not.toHaveBeenCalled();
  });

  it("does nothing when enabled is false", () => {
    const onOpenQuickCreate = vi.fn();
    renderHook(
      () => useKeyboardShortcuts({ role: "coach", enabled: false, onOpenQuickCreate }),
      { wrapper },
    );
    press("n");
    pressChord("i");
    expect(onOpenQuickCreate).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("ignores keys with a modifier held (lets browser/OS shortcuts through)", () => {
    const onOpenQuickCreate = vi.fn();
    renderHook(() => useKeyboardShortcuts({ role: "coach", onOpenQuickCreate }), {
      wrapper,
    });
    press("n", window, { metaKey: true });
    expect(onOpenQuickCreate).not.toHaveBeenCalled();
  });
});
