/**
 * Dark-mode activation (feature 033, US5 / FR-008, optional story).
 *
 * Pure client-side preference — never persisted server-side, never affects
 * generated documents (FR-010). Applied by toggling `data-theme` on
 * `<html>`, per `specs/033-visual-coherence-polish/contracts/dark-theme-tokens.md`.
 *
 * Scoped to coach surfaces only: `AppShell` (the one shared layout
 * component rendered for every authenticated role, `frontend/src/routes/ProtectedRoute.tsx`)
 * is the single place that decides, from the *same* `user.role` field
 * `UserMenu`/`AppShell` already use to distinguish coach vs. parent, whether
 * to honor the stored preference (coach/admin) or force `"light"` (parent
 * portal — explicitly out of scope for this story). See `applyParentSurfaceTheme`.
 *
 * The `index.html` pre-hydration `<script>` duplicates `THEME_STORAGE_KEY`
 * and the same "parent → force light" rule inline (it cannot import this
 * module) so the very first paint is already correct — this module is the
 * source of truth those inline constants must be kept in sync with.
 */

export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "tyr:theme-preference:v1";

const VALID_PREFERENCES: ThemePreference[] = ["system", "light", "dark"];

function isThemePreference(value: unknown): value is ThemePreference {
  return (
    typeof value === "string" &&
    (VALID_PREFERENCES as string[]).includes(value)
  );
}

/** Reads the stored preference; defaults to `"system"` for missing/invalid values. */
export function getStoredThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(raw) ? raw : "system";
  } catch {
    // localStorage indisponible (modo privado / cuota agotada) — degrada a
    // "system", que es un no-op visual (sigue prefers-color-scheme).
    return "system";
  }
}

/** Persists the preference. Swallows storage errors (private mode/quota) — the
 * toggle still works in-memory for the current tab even if it can't persist. */
export function setStoredThemePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Mejor-esfuerzo — ver comentario en getStoredThemePreference.
  }
}

/**
 * Applies `data-theme` on `<html>` for a coach/admin surface:
 * `"system"` clears the attribute (falls back to the `prefers-color-scheme`
 * CSS rule); `"light"`/`"dark"` set it explicitly (always wins over the OS
 * preference, per the contract's cascade).
 */
export function applyCoachTheme(preference: ThemePreference): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (preference === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = preference;
  }
}

/**
 * Forces light mode regardless of the stored preference or OS setting — the
 * parent portal is explicitly out of scope for dark mode (contracts/dark-theme-tokens.md
 * "Activation rules / scope guardrails"). Setting `data-theme="light"` (not
 * just clearing the attribute) is required: an unset attribute still falls
 * back to `prefers-color-scheme: dark` on the user's OS.
 */
export function applyParentSurfaceTheme(): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = "light";
}
