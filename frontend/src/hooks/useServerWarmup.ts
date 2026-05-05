import { useEffect, useState } from "react";
import { apiClient } from "@/api/client";

export function useServerWarmup() {
  const [isWarm, setIsWarm] = useState(false);
  const [isWarming, setIsWarming] = useState(true);

  useEffect(() => {
    let cancelled = false;

    apiClient
      .get("/health")
      .then(() => {
        if (!cancelled) {
          setIsWarm(true);
          setIsWarming(false);
        }
      })
      .catch(() => {
        // Silencioso — el login reportará el error si el backend está caído
        if (!cancelled) setIsWarming(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { isWarm, isWarming };
}
