import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useFormDraft — autoguardado local (debounced) de un formulario y restauración
 * tras interrupciones (recarga, cierre de pestaña, pérdida de conexión).
 *
 * Diseño y privacidad:
 *  - Clave aislada por usuario y por destino: `tyr:session-draft:v1:{userId}:{target}`
 *    (target = "new" o el id de la sesión en edición). Evita que una tablet
 *    familiar restaure el borrador de otra cuenta (mismo criterio que el
 *    aislamiento de caché "Privacy R2").
 *  - Los borradores pueden contener ids de atletas (dato sensible de menores):
 *    NUNCA se registran en logs y se limpian al guardar o descartar.
 *  - Guardas SSR/quota: todo acceso a localStorage va envuelto en try/catch.
 *  - Expiración: un borrador con más de `DRAFT_TTL_MS` (24 h, alineado con
 *    "dentro del mismo día" del spec 046 US1 #7) se descarta al leerlo en
 *    vez de ofrecerse para restaurar (privacy-audit F8). Además, `logout()`
 *    (`auth.store.ts`) llama a `clearAllDrafts()` para borrar cualquier
 *    borrador — vigente o no — de la tablet compartida.
 */

const DRAFT_VERSION = "v1";
const KEY_PREFIX = "tyr:session-draft";
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

export interface FormDraft<T> {
  version: string;
  values: T;
  step: number;
  updatedAt: string;
}

function buildKey(userId: number | null, target: string): string {
  return `${KEY_PREFIX}:${DRAFT_VERSION}:${userId ?? "anon"}:${target}`;
}

function safeGet(key: string): string | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;
    window.localStorage.setItem(key, value);
  } catch {
    // Quota / modo privado: degradar silenciosamente (el borrador es best-effort).
  }
}

function safeRemove(key: string): void {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;
    window.localStorage.removeItem(key);
  } catch {
    /* noop */
  }
}

/**
 * Borra todo borrador persistido (cualquier usuario/destino) al hacer
 * logout, para que una tablet compartida no arrastre un borrador entre
 * cuentas (privacy-audit F8).
 */
export function clearAllDrafts(): void {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key && key.startsWith(`${KEY_PREFIX}:`)) keys.push(key);
    }
    for (const key of keys) window.localStorage.removeItem(key);
  } catch {
    /* noop */
  }
}

export interface UseFormDraftOptions {
  userId: number | null;
  /** "new" para creación, o el id de la sesión en edición. */
  target: string;
  /** Si false, no se lee ni escribe (p. ej. mientras carga la sesión a editar). */
  enabled?: boolean;
  /** Retardo de debounce en ms. */
  debounceMs?: number;
}

export interface UseFormDraft<T> {
  /** Borrador encontrado al montar (null si no hay). Se ofrece para restaurar. */
  restoreCandidate: FormDraft<T> | null;
  /** Persiste valores + paso (debounced). */
  saveDraft: (values: T, step: number) => void;
  /** Borra el borrador (al guardar con éxito o al descartar). */
  clearDraft: () => void;
}

export function useFormDraft<T>({
  userId,
  target,
  enabled = true,
  debounceMs = 800,
}: UseFormDraftOptions): UseFormDraft<T> {
  const key = buildKey(userId, target);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Último valor pasado a `saveDraft` todavía no persistido (el debounce
  // sigue en vuelo) — lo necesita el flush síncrono de `pagehide`/
  // `beforeunload` de abajo.
  const pendingRef = useRef<{ values: T; step: number } | null>(null);

  // Leemos el candidato a restaurar UNA vez al montar (no reactivo a cambios
  // posteriores de localStorage, para no re-ofrecer tras restaurar/descartar).
  const [restoreCandidate] = useState<FormDraft<T> | null>(() => {
    if (!enabled) return null;
    const raw = safeGet(key);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as FormDraft<T>;
      if (parsed && parsed.version === DRAFT_VERSION && parsed.values) {
        const updatedAt = Date.parse(parsed.updatedAt);
        const isExpired = !Number.isNaN(updatedAt) && Date.now() - updatedAt > DRAFT_TTL_MS;
        if (isExpired) {
          safeRemove(key);
          return null;
        }
        return parsed;
      }
      return null;
    } catch {
      return null;
    }
  });

  const persist = useCallback(
    (values: T, step: number) => {
      const draft: FormDraft<T> = {
        version: DRAFT_VERSION,
        values,
        step,
        updatedAt: new Date().toISOString(),
      };
      safeSet(key, JSON.stringify(draft));
      pendingRef.current = null;
    },
    [key],
  );

  const saveDraft = useCallback(
    (values: T, step: number) => {
      if (!enabled) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      pendingRef.current = { values, step };
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        persist(values, step);
      }, debounceMs);
    },
    [enabled, debounceMs, persist],
  );

  const clearDraft = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    pendingRef.current = null;
    safeRemove(key);
  }, [key]);

  // Flush síncrono: si hay un guardado debounced todavía pendiente cuando la
  // pestaña se recarga/cierra, el timeout nunca llega a disparar y el
  // borrador se pierde — justo el escenario ("recarga a mitad de captura")
  // que esta función existe para cubrir. `pagehide` corre de forma
  // confiable en recarga/navegación/cierre (a diferencia de `beforeunload`,
  // cada vez más restringido por los navegadores); se registran ambos por
  // compatibilidad. `localStorage.setItem` es síncrono, así que es seguro
  // llamarlo desde estos handlers.
  useEffect(() => {
    function flushPending() {
      if (timerRef.current && pendingRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
        persist(pendingRef.current.values, pendingRef.current.step);
      }
    }
    window.addEventListener("pagehide", flushPending);
    window.addEventListener("beforeunload", flushPending);
    return () => {
      window.removeEventListener("pagehide", flushPending);
      window.removeEventListener("beforeunload", flushPending);
    };
  }, [persist]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { restoreCandidate, saveDraft, clearDraft };
}
