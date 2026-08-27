/**
 * useSidebarCollapsed — estado colapsado/expandido de la barra lateral del
 * entrenador (feature 035, riel de 72px).
 *
 * Reglas:
 *  - El control es SIEMPRE manual (el botón del encabezado de `SidebarNav`).
 *    El hook no escucha cambios de viewport después del montaje: si el
 *    entrenador expandió la barra en su tablet, rotar el dispositivo no se la
 *    vuelve a plegar.
 *  - La elección se persiste en `localStorage` y gana sobre cualquier default.
 *  - Sin valor almacenado, el default sale de `matchMedia`: en el rango de
 *    tablet (768–1023px) arranca en riel — el entrenador en campo prioriza el
 *    área de contenido; en móvil (<768px) manda la `BottomNav` y en escritorio
 *    (≥1024px) la barra arranca expandida.
 *
 * Todo acceso a `window`/`localStorage`/`matchMedia` va guardado (SSR y jsdom
 * sin polyfill de matchMedia degradan a "expandida", nunca lanzan).
 */
import { useCallback, useRef, useState } from "react";

/** Clave de persistencia — versionada, mismo patrón que `tyr:theme-preference:v1`. */
export const SIDEBAR_COLLAPSED_STORAGE_KEY = "tyr:nav-collapsed:v1";

/** Rango tablet: única franja donde el riel es el default sugerido. */
export const SIDEBAR_RAIL_DEFAULT_QUERY =
  "(min-width: 768px) and (max-width: 1023px)";

export interface UseSidebarCollapsedResult {
  collapsed: boolean;
  toggle: () => void;
}

/** Preferencia almacenada, o `null` si no hay ninguna (o el storage falla). */
function readStoredCollapsed(): boolean | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  try {
    const raw = window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    if (raw === "true") return true;
    if (raw === "false") return false;
    return null;
  } catch {
    // localStorage indisponible (modo privado / cuota) — se usa el default.
    return null;
  }
}

/** Persiste la elección. Mejor-esfuerzo: si falla, el toggle igual funciona en memoria. */
function writeStoredCollapsed(collapsed: boolean): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(
      SIDEBAR_COLLAPSED_STORAGE_KEY,
      collapsed ? "true" : "false",
    );
  } catch {
    // Ver comentario en readStoredCollapsed.
  }
}

/** `true` sólo dentro del rango tablet. jsdom no implementa matchMedia → false. */
function prefersRailByViewport(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia(SIDEBAR_RAIL_DEFAULT_QUERY).matches;
  } catch {
    return false;
  }
}

export function useSidebarCollapsed(): UseSidebarCollapsedResult {
  // Inicializador perezoso: se evalúa una sola vez, en el primer render.
  const [collapsed, setCollapsed] = useState<boolean>(
    () => readStoredCollapsed() ?? prefersRailByViewport(),
  );

  // Espejo en ref para que `toggle` sea estable y NO escriba en localStorage
  // dentro del updater de `setState` (React 19 puede reinvocarlo).
  const collapsedRef = useRef(collapsed);
  collapsedRef.current = collapsed;

  const toggle = useCallback(() => {
    const next = !collapsedRef.current;
    collapsedRef.current = next;
    writeStoredCollapsed(next);
    setCollapsed(next);
  }, []);

  return { collapsed, toggle };
}
