/**
 * Keyboard-shortcuts hook (feature 033, US5, T062).
 *
 * Bindings:
 *  - `g` then `i/e/c/a/f` — jump to the five 030 `NavArea`s: Inicio,
 *    Entrenamiento, Competencias, Atletas, Familias (in
 *    `frontend/src/lib/navigation.ts`, the single source of truth also
 *    consumed by `SidebarNav`/`BottomNav`/`MoreSheet`). Navigates to
 *    `resolveAreaDefaultTo(area, role)` — the same default target the nav
 *    itself would send that role to — and is a no-op if the area (or its
 *    resolved default) isn't visible to `role`.
 *  - `n` — opens the existing `QuickCreate` control. This hook does not
 *    render or import `QuickCreate` itself (that integration is a later
 *    task, T063-adjacent); it only invokes `onOpenQuickCreate` if the
 *    caller supplied one.
 *  - `?` — opens the shortcuts-help dialog. The dialog is built by a later
 *    task (T063); this hook just invokes `onOpenShortcutsHelp` if supplied.
 *
 * Guardrails (both required, either one suppresses every binding below):
 *  - Typing focus: `document.activeElement` is an `<input>`, `<textarea>`,
 *    or `[contenteditable]`.
 *  - An overlay is open: any element with `[data-state="open"]` exists in
 *    the DOM. This is the same Radix attribute `ui/dialog.tsx`, `ui/sheet.tsx`,
 *    and `ui/dropdown-menu.tsx` already render on their portaled
 *    Content/Overlay while open (and remove once closed) — reused here
 *    instead of inventing new global "is a dialog open" state.
 *
 * Mount point: `AppShell` (feature 035). Se llama exactamente una vez por
 * shell autenticado — con `enabled: false` para el rol parent, que no tiene
 * `NavArea`s a las que saltar. Antes vivía dentro de `UserMenu`, que ahora se
 * monta dos veces en el shell de entrenador (pie de la barra lateral + header
 * bajo `md`) y registraría los mismos atajos por duplicado.
 */
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import { NAV_AREAS, resolveAreaDefaultTo, type NavRole } from "@/lib/navigation";

/** Max delay (ms) between `g` and the following area key before the chord resets. */
const CHORD_TIMEOUT_MS = 1500;

/** Second key of the `g` chord -> target `NavArea.id` (frontend/src/lib/navigation.ts). */
export const AREA_ID_BY_SHORTCUT_KEY: Readonly<Record<string, string>> = {
  i: "home",
  e: "training",
  c: "competitions",
  a: "athletes",
  f: "families",
};

export interface UseKeyboardShortcutsOptions {
  /** Current user's role — gates which NavAreas a chord may jump to. */
  role: NavRole;
  /** Invoked when `n` is pressed. Wire to opening `QuickCreate` (later task). */
  onOpenQuickCreate?: () => void;
  /** Invoked when `?` is pressed. Wire to opening the shortcuts-help dialog (T063). */
  onOpenShortcutsHelp?: () => void;
  /** Escape hatch to fully disable the hook, e.g. during a full-page takeover flow. */
  enabled?: boolean;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return true;
  // `isContentEditable` is the spec-correct check, but fall back to the raw
  // attribute too (jsdom's test environment doesn't implement the getter).
  const contentEditableAttr = target.getAttribute("contenteditable");
  return (
    target.isContentEditable === true ||
    contentEditableAttr === "true" ||
    contentEditableAttr === ""
  );
}

/** Any Radix dialog/sheet/dropdown/menu currently rendered open in the DOM. */
function isOverlayOpen(): boolean {
  return document.querySelector('[data-state="open"]') !== null;
}

/**
 * Registers the `g`-chord / `n` / `?` global keyboard shortcuts on `window`.
 * Standalone — does not render anything and is not wired into the app shell.
 */
export function useKeyboardShortcuts({
  role,
  onOpenQuickCreate,
  onOpenShortcutsHelp,
  enabled = true,
}: UseKeyboardShortcutsOptions): void {
  const navigate = useNavigate();
  // Refs (not state) — a chord in flight must never trigger a re-render.
  const chordArmedRef = useRef(false);
  const chordTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    function disarmChord() {
      chordArmedRef.current = false;
      if (chordTimerRef.current !== null) {
        clearTimeout(chordTimerRef.current);
        chordTimerRef.current = null;
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      // Guardrails: typing focus or any open overlay suppresses everything.
      if (isTypingTarget(event.target) || isOverlayOpen()) {
        disarmChord();
        return;
      }
      // Let browser/OS/app modifier shortcuts (Cmd+K, Ctrl+F, ...) pass through untouched.
      if (event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }

      if (chordArmedRef.current) {
        const areaId = AREA_ID_BY_SHORTCUT_KEY[event.key];
        disarmChord();
        if (!areaId) {
          return;
        }
        const area = NAV_AREAS.find((candidate) => candidate.id === areaId);
        if (!area || !area.roles.includes(role)) {
          return;
        }
        const to = resolveAreaDefaultTo(area, role);
        if (!to) {
          return;
        }
        event.preventDefault();
        navigate(to);
        return;
      }

      if (event.key === "g") {
        chordArmedRef.current = true;
        chordTimerRef.current = setTimeout(disarmChord, CHORD_TIMEOUT_MS);
        return;
      }

      if (event.key === "n") {
        if (onOpenQuickCreate) {
          event.preventDefault();
          onOpenQuickCreate();
        }
        return;
      }

      if (event.key === "?") {
        if (onOpenShortcutsHelp) {
          event.preventDefault();
          onOpenShortcutsHelp();
        }
        return;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      disarmChord();
    };
  }, [enabled, navigate, onOpenQuickCreate, onOpenShortcutsHelp, role]);
}
