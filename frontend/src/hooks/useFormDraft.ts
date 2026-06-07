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
 */

const DRAFT_VERSION = "v1";
const KEY_PREFIX = "tyr:session-draft";

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

  // Leemos el candidato a restaurar UNA vez al montar (no reactivo a cambios
  // posteriores de localStorage, para no re-ofrecer tras restaurar/descartar).
  const [restoreCandidate] = useState<FormDraft<T> | null>(() => {
    if (!enabled) return null;
    const raw = safeGet(key);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as FormDraft<T>;
      if (parsed && parsed.version === DRAFT_VERSION && parsed.values) {
        return parsed;
      }
      return null;
    } catch {
      return null;
    }
  });

  const saveDraft = useCallback(
    (values: T, step: number) => {
      if (!enabled) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const draft: FormDraft<T> = {
          version: DRAFT_VERSION,
          values,
          step,
          updatedAt: new Date().toISOString(),
        };
        safeSet(key, JSON.stringify(draft));
      }, debounceMs);
    },
    [enabled, key, debounceMs],
  );

  const clearDraft = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    safeRemove(key);
  }, [key]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { restoreCandidate, saveDraft, clearDraft };
}
