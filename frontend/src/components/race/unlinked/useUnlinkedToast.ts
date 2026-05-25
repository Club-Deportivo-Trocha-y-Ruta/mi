/**
 * useUnlinkedToast — wrapper sobre useState que cierra el toast automáticamente
 * tras 6 segundos (ajustable). Extraído de UnlinkedCompetitorsTab en B5.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { ToastState, ToastVariant } from "./ToastBanner";

export function useUnlinkedToast(autoDismissMs = 6_000) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setToast(null);
  }, []);

  const showToast = useCallback(
    (variant: ToastVariant, message: string) => {
      setToast({ variant, message });
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setToast(null), autoDismissMs);
    },
    [autoDismissMs],
  );

  // Cleanup timer on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { toast, showToast, dismiss };
}
