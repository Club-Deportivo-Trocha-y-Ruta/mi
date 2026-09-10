import { Activity, AlertCircle, Cpu, Loader2, Power } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAIHealth } from "@/hooks/ai/useAIHealth";
import { useAIUsage } from "@/hooks/ai/useAIUsage";
import { cn } from "@/lib/utils";
import type { AIUsageByCoach } from "@/types/raceAnalysis.types";

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  accentClass?: string;
}

function StatCard({ label, value, icon: Icon, accentClass }: StatCardProps) {
  return (
    <div className={cn("flex items-start gap-3 rounded-xl bg-white p-5", "shadow-card")}>
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
          className="font-display mt-1 text-base text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          {value}
        </p>
      </div>
    </div>
  );
}

/** `$X.XXXX` — misma precisión (4 decimales) que usa el backend en
 * `contracts/scope-ai-imports.md` §7.2/§8 para montos de gasto de IA. */
function formatUsd(amount: number): string {
  return `$${amount.toFixed(4)}`;
}

/**
 * Clave estable de fila. El identificador del usuario cuando existe; si no,
 * un slug de la etiqueta del cubo. Los cubos agregados —"Sin atribuir" y, para
 * un entrenador, "Otros clubes"— llegan ambos con `user_id` nulo, así que la
 * clave no puede salir del id o las dos filas colisionarían (feature 041, H3).
 */
function spendRowKey(row: AIUsageByCoach): string {
  if (row.user_id !== null && row.user_id !== undefined) return String(row.user_id);
  return row.display_name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * AISpendByCoachSection — tabla de gasto de IA por entrenador (feature 041,
 * gobernanza multi-coach, US6, §7.3). Consulta independiente de
 * `useAIHealth`: un fallo aquí nunca oculta la tarjeta de proveedor/modelo,
 * y viceversa.
 */
function AISpendByCoachSection() {
  const usageQuery = useAIUsage({ days: 30 });
  const rows: AIUsageByCoach[] = usageQuery.data?.by_coach ?? [];
  const totalRuns = rows.reduce((sum, row) => sum + row.run_count, 0);
  const totalCost = rows.reduce((sum, row) => sum + row.cost_usd_total, 0);
  // Cold start (Render Free despertando, Constitución IV): la copy propia
  // de ErrorState ("La aplicación está iniciando…") reemplaza el mensaje
  // de error genérico — nunca un spinner sin contexto.
  const usageIsColdStart = isColdStartError(usageQuery.error);

  return (
    <section className="space-y-3" aria-labelledby="ai-spend-by-coach-heading">
      <h2
        id="ai-spend-by-coach-heading"
        className="font-display text-lg text-charcoal"
        style={{ letterSpacing: "0.2px" }}
      >
        Gasto de IA por entrenador (últimos 30 días)
      </h2>

      {usageQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4 shadow-card"
          role="status"
          aria-live="polite"
          data-testid="ai-spend-by-coach-loading"
        >
          <span className="sr-only">Cargando gasto de IA por entrenador…</span>
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="h-12 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {usageQuery.isError && !usageQuery.isLoading && (
        <ErrorState
          message={
            usageIsColdStart
              ? undefined
              : "No se pudo cargar el gasto de IA. Intenta de nuevo."
          }
          onRetry={async () => {
            await usageQuery.refetch();
          }}
          isColdStart={usageIsColdStart}
        />
      )}

      {!usageQuery.isLoading && !usageQuery.isError && rows.length === 0 && (
        <EmptyState title="Aún no hay gasto registrado en esta ventana." />
      )}

      {!usageQuery.isLoading && !usageQuery.isError && rows.length > 0 && (
        <div className="rounded-xl bg-white shadow-card">
          <Table data-testid="ai-spend-by-coach-table">
            <caption className="sr-only">Gasto de IA por entrenador</caption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Entrenador</TableHead>
                <TableHead scope="col">Análisis</TableHead>
                <TableHead scope="col">Gasto (USD)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={spendRowKey(row)}
                  className="h-12"
                  data-testid={`ai-spend-row-${spendRowKey(row)}`}
                >
                  <TableCell>{row.display_name}</TableCell>
                  <TableCell className="tabular-nums">{row.run_count}</TableCell>
                  <TableCell className="tabular-nums">
                    {formatUsd(row.cost_usd_total)}
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="h-12 font-semibold" data-testid="ai-spend-row-total">
                <TableCell>Total del club</TableCell>
                <TableCell className="tabular-nums">{totalRuns}</TableCell>
                <TableCell className="tabular-nums">{formatUsd(totalCost)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}

export function AIHealthPage() {
  const { data, isLoading, isError, error } = useAIHealth();

  return (
    <section className="space-y-6 p-6">
      <header>
        <h1
          className="font-display text-2xl text-charcoal"
          style={{ letterSpacing: "0.2px" }}
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
          className={cn(
            "flex items-center gap-3 rounded-xl bg-white p-5 text-sm text-mid-gray",
            "shadow-card",
          )}
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

      <AISpendByCoachSection />
    </section>
  );
}
