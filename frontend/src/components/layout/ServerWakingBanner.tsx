/**
 * ServerWakingBanner — explicit "la aplicación está iniciando…" state
 * (feature 012, US2; copy ajustada por revisión ux-researcher: "aplicación"
 * en lugar de "servidor" para padres no técnicos).
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
        className="mt-1 h-2 w-2 shrink-0 animate-pulse motion-reduce:animate-none rounded-full bg-amber-500"
      />
      <p>
        {/* Copy validada por ux-researcher: "aplicación" en lugar de
            "servidor" — término cotidiano para padres no técnicos. */}
        <span className="font-medium">La aplicación está iniciando…</span>{" "}
        Esto puede tardar unos segundos la primera vez; tu contenido aparecerá
        en cuanto responda.
      </p>
    </div>
  );
}
