import { Activity, AlertCircle, Cpu, Loader2, Power } from "lucide-react";

import { useAIHealth } from "@/hooks/ai/useAIHealth";
import { cn } from "@/lib/utils";

/* shadow-card utility */
interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  accentClass?: string;
}

function StatCard({ label, value, icon: Icon, accentClass }: StatCardProps) {
  return (
    <div
      className="flex items-start gap-3 rounded-xl bg-white p-5"
    >
      <div
        className={cn(
          "rounded-lg p-2",
          accentClass ?? "bg-blue-100 text-blue-700",
        )}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-mid-gray">{label}</p>
        <p
          className="mt-1 text-base text-charcoal font-heading tracking-[0.2px]"
        >
          {value}
        </p>
      </div>
    </div>
  );
}

export function AIHealthPage() {
  const { data, isLoading, isError, error } = useAIHealth();

  return (
    <section className="space-y-6 p-6">
      <header>
        <h1
          className="text-2xl text-charcoal font-heading tracking-[0.2px]"
        >
          Estado de la capa de IA
        </h1>
        <p className="mt-1 text-sm text-mid-gray">
          Diagnóstico del proveedor LLM activo. Útil al detectar cold starts
          en producción o validar la configuración tras cambios de variables.
        </p>
      </header>

      {isLoading && (
        <div
          className="flex items-center gap-3 rounded-xl bg-white p-5 text-sm text-mid-gray"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Consultando estado…
        </div>
      )}

      {isError && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-5"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 text-red-600" />
          <div className="text-sm text-red-700">
            <p className="font-semibold">No se pudo obtener el estado.</p>
            <p className="mt-1">
              Verifica que tienes rol admin y que el backend esté
              respondiendo. Detalle: {(error as Error)?.message ?? "desconocido"}.
            </p>
          </div>
        </div>
      )}

      {data && (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Estado"
            value={
              data.enabled ? (
                <span className="text-green-700">Habilitado</span>
              ) : (
                <span className="text-amber-700">Deshabilitado</span>
              )
            }
            icon={Power}
            accentClass={
              data.enabled
                ? "bg-green-100 text-green-700"
                : "bg-amber-100 text-amber-700"
            }
          />
          <StatCard label="Proveedor" value={data.provider} icon={Cpu} />
          <StatCard
            label="Modelo"
            value={data.model}
            icon={Activity}
            accentClass="bg-purple-100 text-purple-700"
          />
        </div>
      )}

      <p className="text-xs text-mid-gray">
        Para cambiar el proveedor o modelo, ajusta las variables{" "}
        <code className="rounded bg-light-gray px-1">AI_PROVIDER</code>,{" "}
        <code className="rounded bg-light-gray px-1">AI_MODEL</code> y{" "}
        <code className="rounded bg-light-gray px-1">AI_API_KEY</code> en el
        servicio del backend (Render → Environment).
      </p>
    </section>
  );
}
