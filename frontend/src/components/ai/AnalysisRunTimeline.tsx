/**
 * Timeline visual del run agéntico (race-analysis §10.2 #AnalysisRunTimeline).
 *
 * Renderiza los 13 nodos del grafo LangGraph (workflow §"Fase 4") en
 * orden, marcando cada uno como pending / running / done / error según
 * los eventos llegados por polling.
 *
 * Cada nodo:
 *  - Ícono lucide específico.
 *  - Label español.
 *  - Status badge.
 *  - Duración (ms) calculada como diff entre `node_start` y `node_end`.
 *
 * Accesibilidad:
 *  - aria-live="polite" para que un screen reader anuncie cambios sin
 *    interrumpir la lectura del usuario.
 *  - Cada nodo es un `<li>` semántico, el wrapper es un `<ol>`.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Bot,
  Brain,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Database,
  FileText,
  Loader2,
  Mail,
  PauseCircle,
  Save,
  ScanText,
  Send,
  ShieldCheck,
  TrendingUp,
  User,
  type LucideIcon,
} from "lucide-react";

import { useRunStatus, isTerminalState } from "@/hooks/ai/useRaceRun";
import { cn } from "@/lib/utils";
import type { RunEvent, RunState } from "@/types/raceAnalysis.types";

interface NodeDef {
  key: string;
  label: string;
  icon: LucideIcon;
}

/** Catálogo de nodos esperados — diseño v2 §4.1 + §4.3.
 *
 * El orden lógico es lineal con un loop opcional analyst↔critic. Aquí
 * usamos la sucesión completa típica para ayudar al coach a entender
 * en qué fase está. Si el backend introduce nodos nuevos, llegarán
 * como `unknown` y se renderizan al final.
 */
const GRAPH_NODES: NodeDef[] = [
  { key: "validate_input", label: "Validar input", icon: ClipboardCheck },
  { key: "load_race_data", label: "Cargar datos de carrera", icon: Database },
  { key: "anonymize", label: "Anonimizar datos", icon: ShieldCheck },
  { key: "compute_metrics", label: "Calcular métricas", icon: TrendingUp },
  { key: "retrieve_principles", label: "Recuperar principios LTAD", icon: ScanText },
  { key: "recall_memory", label: "Recordar contexto previo", icon: Brain },
  { key: "analyst_agent", label: "Agente analista", icon: Bot },
  { key: "critic_agent", label: "Agente crítico", icon: AlertCircle },
  { key: "hitl_gate_review", label: "Revisión humana (HITL)", icon: User },
  { key: "persist_insight", label: "Guardar insight", icon: Save },
  { key: "rehydrate_names", label: "Rehidratar nombres", icon: ShieldCheck },
  { key: "render_outputs", label: "Renderizar informe", icon: FileText },
  { key: "notify_coach", label: "Notificar al coach", icon: Mail },
];

/**
 * Traducción de nodo del grafo → fase en lenguaje de entrenador.
 *
 * Los 13 nodos de `GRAPH_NODES` son vocabulario de ingeniería ("Anonimizar
 * datos", "Rehidratar nombres"): describen el pipeline, no lo que le importa
 * a quien dirige el club. En la vista compacta mostramos SOLO la fase actual
 * con estas etiquetas; el detalle por nodo sigue disponible al expandir.
 *
 * Varios nodos comparten fase a propósito — el coach no necesita distinguir
 * entre anonimizar y calcular métricas, ambas son "preparando los datos".
 */
const PHASE_BY_NODE: Record<string, string> = {
  validate_input: "Leyendo los resultados oficiales",
  load_race_data: "Leyendo los resultados oficiales",
  anonymize: "Preparando los datos de la carrera",
  compute_metrics: "Preparando los datos de la carrera",
  retrieve_principles: "Comparando con la temporada",
  recall_memory: "Comparando con la temporada",
  analyst_agent: "Redactando el análisis",
  critic_agent: "Revisando la calidad del análisis",
  hitl_gate_review: "Esperando tu aprobación",
  persist_insight: "Guardando el informe",
  rehydrate_names: "Guardando el informe",
  render_outputs: "Guardando el informe",
  notify_coach: "Guardando el informe",
};

/** Titular del run: fase actual si está corriendo, si no el estado global. */
function runHeadline(state: RunState, currentNode: string | null): string {
  if (state === "hitl_waiting") return "Esperando tu aprobación";
  if (state === "done") return "Análisis completado";
  if (state === "failed" || state === "error") return "El análisis falló";
  if (state === "cancelled") return "Análisis descartado";
  return (currentNode && PHASE_BY_NODE[currentNode]) || "Preparando el análisis";
}

type NodeStatus =
  | "pending"
  | "running"
  | "done"
  | "error"
  | "awaiting_review";

/** Nodo del grafo donde el flujo puede pausarse esperando aprobación coach
 * (HITL gate). Cuando el state global del run es `hitl_waiting`, los
 * eventos `error`/`node_error` emitidos en este nodo son la representación
 * defensiva de una `GraphInterrupt` interna de LangGraph, NO un fallo. */
const HITL_GATE_NODE = "hitl_gate_review";

interface NodeView extends NodeDef {
  status: NodeStatus;
  durationMs: number | null;
}

/** Reduce la lista plana de eventos al status por nodo + duraciones.
 *
 * Reglas:
 *  - `node_start` → marca running (si aún no terminó).
 *  - `node_end`   → marca done con duración (now - start).
 *  - `node_error` o `type=error` → marca error.
 *  - sin eventos del nodo → pending.
 *
 * Override defensivo (HITL):
 *  - Si `globalState === "hitl_waiting"` y el evento `error`/`node_error`
 *    pertenece al nodo `hitl_gate_review`, se interpreta como pausa
 *    esperando revisión (NodeStatus `awaiting_review`), no como fallo.
 *    Esto cubre el caso en que LangGraph emite una `GraphInterrupt` que
 *    el decorador `with_events` del backend serializa como `event_type=error`.
 */
function reduceNodeStatuses(
  events: RunEvent[],
  globalState: RunState,
): Map<string, { status: NodeStatus; durationMs: number | null }> {
  const map = new Map<
    string,
    { startTs?: number; endTs?: number; status: NodeStatus }
  >();
  for (const evt of events) {
    const node = evt.node;
    if (!node) continue;
    const entry = map.get(node) ?? { status: "pending" as NodeStatus };
    const tsMs = new Date(evt.ts).getTime();
    switch (evt.type) {
      case "node_start":
        entry.startTs = tsMs;
        if (entry.status === "pending") entry.status = "running";
        break;
      case "node_end":
      case "node_complete":
        entry.endTs = tsMs;
        entry.status = "done";
        break;
      case "node_error":
      case "error":
        // Override HITL: si el grafo está pausado esperando coach y el
        // evento error pertenece al gate HITL, NO marcamos error.
        // El gate queda en "awaiting_review" — pausa intencional.
        if (node === HITL_GATE_NODE && globalState === "hitl_waiting") {
          entry.status = "awaiting_review";
        } else {
          entry.status = "error";
          entry.endTs = tsMs;
        }
        break;
      default:
        // explain, hitl_request, hitl_response, etc → no cambian status,
        // pero si llegan antes de un explicit start, dejan el nodo como
        // running para mostrar actividad.
        if (entry.status === "pending") entry.status = "running";
    }
    map.set(node, entry);
  }
  const out = new Map<string, { status: NodeStatus; durationMs: number | null }>();
  for (const [key, val] of map) {
    let duration: number | null = null;
    if (val.startTs !== undefined && val.endTs !== undefined) {
      duration = Math.max(0, val.endTs - val.startTs);
    }
    out.set(key, { status: val.status, durationMs: duration });
  }
  return out;
}

interface AnalysisRunTimelineProps {
  runId: string;
  className?: string;
  /** Llamado una sola vez cuando el run alcanza estado terminal (done/failed/cancelled). */
  onComplete?: () => void;
  /**
   * `"full"` (default) renderiza el header + la lista `<ol>` de los 13 nodos.
   * `"compact"` renderiza solo el header (label de estado + barra de progreso
   * + ETA) — misma máquina de estados, sin el detalle por nodo. Pensado para
   * filas de tabla (`GroupRunRow`) donde el espacio es limitado: un solo
   * componente de run-view, dos densidades.
   */
  variant?: "full" | "compact";
  /**
   * Renderiza la vista compacta con un botón "Ver detalle" que despliega la
   * lista de nodos bajo demanda. Pensado para la vista por deportista: los 13
   * nodos del pipeline ocupaban ~470px y empujaban el histórico —el contenido
   * que el coach realmente viene a leer— fuera de la pantalla. El detalle
   * técnico sigue a un clic para diagnosticar un run atascado.
   */
  collapsible?: boolean;
}

function statusBadge(status: NodeStatus): {
  icon: React.ReactNode;
  label: string;
  cls: string;
} {
  switch (status) {
    case "done":
      return {
        icon: <CheckCircle2 size={14} aria-hidden="true" />,
        label: "Completado",
        cls: "bg-green-100 text-green-800",
      };
    case "running":
      return {
        icon: <Loader2 size={14} className="animate-spin" aria-hidden="true" />,
        label: "En curso",
        cls: "bg-blue-100 text-blue-800",
      };
    case "error":
      return {
        icon: <AlertCircle size={14} aria-hidden="true" />,
        label: "Error",
        cls: "bg-red-100 text-red-800",
      };
    case "awaiting_review":
      return {
        icon: <PauseCircle size={14} aria-hidden="true" />,
        label: "Esperando revisión",
        cls: "bg-purple-100 text-purple-800",
      };
    case "pending":
    default:
      return {
        icon: <span className="h-2 w-2 rounded-full bg-mid-gray" />,
        label: "Pendiente",
        cls: "bg-light-gray text-mid-gray",
      };
  }
}

export function AnalysisRunTimeline({
  runId,
  className,
  onComplete,
  variant = "full",
  collapsible = false,
}: AnalysisRunTimelineProps) {
  const query = useRunStatus(runId);
  const { data, isLoading, isError, error } = query;
  const [detailOpen, setDetailOpen] = useState(false);
  const showNodeList = collapsible ? detailOpen : variant === "full";

  const nodes: NodeView[] = useMemo(() => {
    if (!data) return GRAPH_NODES.map((n) => ({ ...n, status: "pending" as NodeStatus, durationMs: null }));
    const reduced = reduceNodeStatuses(data.events, data.latest.state);
    const knownKeys = new Set(GRAPH_NODES.map((n) => n.key));
    const enriched: NodeView[] = GRAPH_NODES.map((n) => {
      const s = reduced.get(n.key);
      return { ...n, status: s?.status ?? "pending", durationMs: s?.durationMs ?? null };
    });
    // Añadir nodos desconocidos al final (defensive, por si backend cambia).
    for (const [key, val] of reduced) {
      if (!knownKeys.has(key)) {
        enriched.push({
          key,
          label: key,
          icon: Send,
          status: val.status,
          durationMs: val.durationMs,
        });
      }
    }
    return enriched;
  }, [data]);

  // Notificar al caller cuando el run llega a estado terminal.
  const completedRef = useRef(false);
  useEffect(() => {
    if (!data || completedRef.current) return;
    if (isTerminalState(data.latest.state)) {
      completedRef.current = true;
      onComplete?.();
    }
  }, [data, onComplete]);

  // Auto-scroll al nodo activo cuando llega un nuevo evento.
  const activeRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    if (!activeRef.current) return;
    try {
      activeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    } catch {
      /* jsdom no implementa scrollIntoView; ignoramos. */
    }
  }, [data?.latest.current_node, data?.latest.last_seq]);

  if (!runId) {
    return (
      <div className="rounded-xl bg-light-gray/40 p-6 text-center text-sm text-mid-gray">
        Sin run activo. Inicia un análisis para ver el progreso.
      </div>
    );
  }

  if (isLoading && !data) {
    return (
      <div
        className={cn("space-y-2", className)}
        data-testid="timeline-loading"
        aria-live="polite"
      >
        <div className="h-8 w-1/2 animate-pulse rounded-md bg-light-gray" />
        <div className="h-8 w-2/3 animate-pulse rounded-md bg-light-gray" />
        <div className="h-8 w-1/3 animate-pulse rounded-md bg-light-gray" />
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        data-testid="timeline-error"
      >
        <p className="font-semibold">Error obteniendo el estado del análisis</p>
        <p className="mt-1 text-xs">
          {error instanceof Error ? error.message : "Error desconocido"}
        </p>
      </div>
    );
  }

  const state: RunState = data?.latest.state ?? "running";
  const progress = data?.latest.progress_pct ?? 0;
  const eta = data?.latest.estimated_seconds_remaining ?? 0;
  const currentNode = data?.latest.current_node ?? null;

  return (
    <section
      className={cn("space-y-4", className)}
      aria-label="Timeline del análisis"
      data-testid="analysis-run-timeline"
    >
      <div
        className="rounded-xl bg-white p-4 ring-1 ring-light-gray"
        aria-live="polite"
        aria-atomic="true"
      >
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          {/* Titular = fase actual en lenguaje de coach (no el nodo técnico).
              El ícono da la señal de "está pasando algo" que se pierde al
              quitar la lista de 13 nodos de la vista por defecto. */}
          <p
            className="flex items-center gap-2 text-sm font-semibold text-charcoal"
            data-testid="timeline-headline"
          >
            {state === "running" && (
              <Loader2
                size={15}
                className="shrink-0 animate-spin text-mid-gray"
                aria-hidden="true"
              />
            )}
            {state === "hitl_waiting" && (
              <PauseCircle
                size={15}
                className="shrink-0 text-purple-600"
                aria-hidden="true"
              />
            )}
            {state === "done" && (
              <CheckCircle2
                size={15}
                className="shrink-0 text-green-600"
                aria-hidden="true"
              />
            )}
            {(state === "failed" || state === "error") && (
              <AlertCircle
                size={15}
                className="shrink-0 text-red-600"
                aria-hidden="true"
              />
            )}
            {runHeadline(state, currentNode)}
          </p>
          {!isTerminalState(state) && (
            <p
              className="text-xs tabular-nums text-mid-gray"
              data-testid="timeline-eta"
            >
              {eta > 0 ? `≈ ${eta}s restantes` : "Calculando…"}
            </p>
          )}
        </div>
        <div className="mt-2 flex items-center gap-3">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-light-gray"
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Progreso del análisis"
          >
            <div
              className={cn(
                "h-full transition-all duration-300",
                state === "failed" || state === "error"
                  ? "bg-red-500"
                  : "bg-charcoal",
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="shrink-0 text-xs tabular-nums text-mid-gray">
            {progress}%
          </span>
        </div>

        {collapsible && (
          <button
            type="button"
            onClick={() => setDetailOpen((v) => !v)}
            className={cn(
              "mt-1 -mb-1 -ml-2 flex min-h-12 items-center gap-1 rounded-lg px-2 text-xs text-mid-gray",
              "transition-colors hover:bg-light-gray/50 hover:text-charcoal",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
            )}
            aria-expanded={detailOpen}
            aria-controls={`timeline-detail-${runId}`}
            data-testid="timeline-detail-toggle"
          >
            {detailOpen ? "Ocultar detalle técnico" : "Ver detalle técnico"}
            <ChevronDown
              size={13}
              aria-hidden="true"
              className={cn("transition-transform", detailOpen && "rotate-180")}
            />
          </button>
        )}
      </div>

      {showNodeList && (
      <ol
        className="space-y-2"
        id={`timeline-detail-${runId}`}
        data-testid="timeline-nodes-list"
        aria-label="Lista de nodos del grafo"
      >
        {nodes.map((node) => {
          const isActive =
            node.status === "running" ||
            node.status === "awaiting_review" ||
            node.key === currentNode;
          const badge = statusBadge(node.status);
          const Icon = node.icon;
          return (
            <li
              key={node.key}
              ref={isActive ? activeRef : undefined}
              data-testid={`timeline-node-${node.key}`}
              data-status={node.status}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 transition-colors",
                node.status === "awaiting_review"
                  ? "bg-purple-50 ring-1 ring-purple-200"
                  : isActive
                  ? "bg-blue-50 ring-1 ring-blue-200"
                  : "bg-white ring-1 ring-light-gray",
              )}
              aria-label={
                node.status === "awaiting_review"
                  ? `${node.label}: esperando revisión del entrenador`
                  : undefined
              }
            >
              <Icon
                size={18}
                className={cn(
                  node.status === "done"
                    ? "text-green-700"
                    : node.status === "error"
                    ? "text-red-700"
                    : node.status === "awaiting_review"
                    ? "text-purple-700"
                    : node.status === "running"
                    ? "text-blue-700"
                    : "text-mid-gray",
                )}
                aria-hidden="true"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-charcoal truncate">
                  {node.label}
                </p>
                {node.durationMs !== null && (
                  <p className="text-xs text-mid-gray">
                    {node.durationMs < 1000
                      ? `${node.durationMs} ms`
                      : `${(node.durationMs / 1000).toFixed(1)} s`}
                  </p>
                )}
              </div>
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                  badge.cls,
                )}
                aria-label={badge.label}
              >
                {badge.icon}
                <span className="sr-only">{badge.label}</span>
              </span>
            </li>
          );
        })}
      </ol>
      )}
    </section>
  );
}
