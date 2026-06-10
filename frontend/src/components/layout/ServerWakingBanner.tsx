/**
 * ServerWakingBanner — explicit "el servidor está despertando…" state
 * (feature 012, US2).
 *
 * Render Free duerme tras ~15 min de inactividad y tarda ~50 s en despertar.
 * Cuando una petición supera el umbral (~3 s) mostramos este aviso en lugar de
 * un spinner indefinido o un error de timeout; desaparece solo cuando la
 * respuesta llega. Usa los tokens "ámbar = atención" (consistente con
 * MeasurementAlerts) y es accesible (role="status" + aria-live="polite").
 */
import { useServerWakingStore } from "@/store/serverWaking.store";

export function ServerWakingBanner() {
  const isWaking = useServerWakingStore((s) => s.isWaking);
  if (!isWaking) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900"
    >
      <span
        aria-hidden="true"
        className="mt-1 h-2 w-2 shrink-0 animate-pulse rounded-full bg-amber-500"
      />
      <p>
        <span className="font-medium">El servidor está despertando…</span>{" "}
        Esto puede tardar unos segundos la primera vez; tu contenido aparecerá
        en cuanto responda.
      </p>
    </div>
  );
}
