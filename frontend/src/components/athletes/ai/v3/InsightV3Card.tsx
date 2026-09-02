/**
 * InsightV3Card — vista estructurada de un `InsightV3` (feature 037, T301).
 *
 * Reemplaza el markdown plano de v2 por bloques semánticos: titular,
 * "Lectura del pelotón" (field_reading), observaciones con evidencia,
 * checklist de acciones, señales a vigilar, pregunta para el coach (con
 * slot `footer` para `CoachAnswerForm`) y principios citados.
 *
 * Privacidad Ley 1581 (CLAUDE.md §Privacidad de menores):
 *   - `mode="parent"` oculta esperado-vs-real (`field_reading.expected_position`
 *     / `actual_position` / `delta_vs_expected`), `coach_question` (+ footer)
 *     y las observaciones de dominio `training` — el backend ya las omite en
 *     el DTO de padres, pero esta card tolera su ausencia (no asume que
 *     lleguen) y las filtra igual del lado cliente por si acaso.
 *   - Ningún campo de `InsightV3` contiene PII de por sí (ver
 *     `types/insightV3.types.ts`), así que el resto del contenido es igual
 *     en ambos modos.
 *
 * `isFallback=true`: el run terminó por el camino de fallo
 * (`deterministic_fallback`) — NO se lee `trend` ni `field_reading` (pueden
 * no reflejar nada real); se muestra el mismo aviso de fallback que
 * `InsightsTimeline.tsx` (`insight-fallback-notice`).
 */
import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Award,
  Bike,
  CloudSun,
  Dumbbell,
  Flag,
  GitBranch,
  HelpCircle,
  History,
  Minus,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  actionCategoryLabel,
  evidenceDomainLabel,
  horizonLabel,
  priorityLabel,
  priorityVariant,
  progressionLabel,
} from "@/lib/insights";
import type {
  EvidenceDomain,
  InsightV3,
  InsightV3Trend,
} from "@/types/insightV3.types";

export interface InsightV3CardProps {
  structured: InsightV3;
  mode: "coach" | "parent";
  /** El run terminó en el camino de fallback — no leer trend/field_reading. */
  isFallback?: boolean;
  /** Montado bajo la pregunta del coach (típicamente `<CoachAnswerForm>`). Ignorado en mode="parent". */
  footer?: ReactNode;
}

const TREND_ICON: Record<InsightV3Trend, React.ElementType> = {
  improving: TrendingUp,
  stable: Minus,
  declining: TrendingDown,
  mixed: GitBranch,
  first_reference: Sparkles,
};

const DOMAIN_ICON: Record<EvidenceDomain, React.ElementType> = {
  race: Flag,
  field: Bike,
  training: Dumbbell,
  maturation: TrendingUp,
  conditions: CloudSun,
  history: History,
};

export function InsightV3Card({
  structured,
  mode,
  isFallback = false,
  footer,
}: InsightV3CardProps) {
  if (isFallback) {
    return (
      <div
        role="status"
        data-testid="insight-fallback-notice"
        className="rounded-xl border border-dashed border-mid-gray/60 bg-light-gray/20 p-4 text-sm text-charcoal"
      >
        <p className="flex items-center gap-2 font-medium">
          <AlertTriangle
            size={14}
            className="shrink-0 text-mid-gray"
            aria-hidden="true"
          />
          Análisis no disponible
        </p>
        <p className="mt-1 text-xs text-mid-gray">
          {mode === "coach"
            ? 'No fue posible generar este análisis. Puedes revisar los datos oficiales en la sección de Resultados, o cerrar esta ventana y usar "Reintentar" en el histórico para volver a intentarlo.'
            : "No fue posible generar este análisis en este momento. Puedes revisar los datos oficiales en la sección de Resultados; tu entrenador podrá volver a intentarlo."}
        </p>
      </div>
    );
  }

  const observations =
    mode === "parent"
      ? structured.observations.filter((o) => o.domain !== "training")
      : structured.observations;
  const showCoachBlock = mode === "coach" && structured.coach_question.length > 0;
  const TrendIcon = TREND_ICON[structured.trend];

  return (
    <div className="space-y-4" data-testid="insight-v3-card">
      {/* Titular */}
      <div className="flex items-start gap-2">
        <TrendIcon
          size={18}
          className="mt-0.5 shrink-0 text-primary"
          aria-hidden="true"
        />
        <div>
          <h3 className="font-display text-base text-charcoal" data-testid="insight-v3-headline">
            {structured.headline}
          </h3>
          <Badge variant="outline" className="mt-1 gap-1">
            {progressionLabel(structured.trend)}
          </Badge>
        </div>
      </div>

      {/* Lectura del pelotón */}
      {structured.field_reading && (
        <FieldReadingBlock
          reading={structured.field_reading}
          mode={mode}
        />
      )}

      <Separator />

      {/* Observaciones */}
      {observations.length > 0 && (
        <section aria-label="Observaciones" className="space-y-2">
          <h4 className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Observaciones
          </h4>
          <ul className="space-y-2">
            {observations.map((obs, idx) => {
              const DomainIcon = DOMAIN_ICON[obs.domain];
              return (
                <li
                  key={idx}
                  data-testid={`insight-v3-observation-${idx}`}
                  className="rounded-lg bg-light-gray/30 p-3"
                >
                  <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-mid-gray">
                    <DomainIcon size={12} aria-hidden="true" />
                    {evidenceDomainLabel(obs.domain)}
                  </div>
                  <p className="mt-1 text-sm text-charcoal">{obs.claim}</p>
                  {obs.evidence.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {obs.evidence.map((ev, evIdx) => (
                        <span
                          key={evIdx}
                          className="rounded-full bg-white px-2 py-0.5 text-[11px] text-mid-gray ring-1 ring-light-gray"
                        >
                          {ev}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Acciones */}
      {structured.actions.length > 0 && (
        <section aria-label="Acciones recomendadas" className="space-y-2">
          <h4 className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Acciones
          </h4>
          <ul className="space-y-2">
            {structured.actions.map((action, idx) => (
              <li
                key={idx}
                data-testid={`insight-v3-action-${idx}`}
                className="flex items-start gap-2 rounded-lg bg-white p-3 ring-1 ring-light-gray"
              >
                <Target
                  size={14}
                  className="mt-0.5 shrink-0 text-primary"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-charcoal">{action.text}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge variant="secondary">
                      {actionCategoryLabel(action.category)}
                    </Badge>
                    <Badge variant={priorityVariant(action.priority)}>
                      {priorityLabel(action.priority)}
                    </Badge>
                    <Badge variant="outline">{horizonLabel(action.horizon)}</Badge>
                    {action.catalog_ref && (
                      <Badge variant="info" className="gap-1">
                        <Award size={11} aria-hidden="true" />
                        {action.catalog_ref.label ?? action.catalog_ref.code}
                      </Badge>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Señales a vigilar */}
      {structured.watch_signals.length > 0 && (
        <section aria-label="Señales a vigilar" className="space-y-1.5">
          <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
            <AlertTriangle size={12} aria-hidden="true" />
            Señales a vigilar
          </h4>
          <ul className="space-y-1">
            {structured.watch_signals.map((signal, idx) => (
              <li
                key={idx}
                data-testid={`insight-v3-watch-signal-${idx}`}
                className="rounded-lg bg-amber-50 px-3 py-1.5 text-sm text-amber-900"
              >
                {signal}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Pregunta para el coach + footer (CoachAnswerForm) */}
      {showCoachBlock && (
        <section
          aria-label="Pregunta para el coach"
          data-testid="insight-v3-coach-question"
          className="space-y-3 rounded-xl border-2 border-primary/20 bg-primary/5 p-4"
        >
          <p className="flex items-start gap-2 text-sm font-medium text-charcoal">
            <HelpCircle
              size={16}
              className="mt-0.5 shrink-0 text-primary"
              aria-hidden="true"
            />
            {structured.coach_question}
          </p>
          {footer}
        </section>
      )}

      {/* Vacíos de datos — tono muted */}
      {structured.data_gaps.length > 0 && (
        <p className="text-xs text-mid-gray" data-testid="insight-v3-data-gaps">
          Datos incompletos: {structured.data_gaps.join(" · ")}
        </p>
      )}

      {/* Principios citados — discreto */}
      {structured.principles_cited.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger
            className="text-[11px] text-mid-gray underline decoration-dotted underline-offset-2 hover:text-charcoal"
            data-testid="insight-v3-principles-trigger"
          >
            Principios citados ({structured.principles_cited.length})
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {structured.principles_cited.map((p, idx) => (
                <li
                  key={idx}
                  className="rounded-full bg-light-gray/50 px-2 py-0.5 text-[11px] text-mid-gray"
                >
                  {p}
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lectura del pelotón (field_reading)
// ---------------------------------------------------------------------------

function deltaSemantics(delta: number): {
  label: string;
  variant: "success" | "destructive" | "secondary";
} {
  if (delta > 0) return { label: `+${delta} vs esperado`, variant: "success" };
  if (delta < 0) return { label: `${delta} vs esperado`, variant: "destructive" };
  return { label: "Igual a lo esperado", variant: "secondary" };
}

function FieldReadingBlock({
  reading,
  mode,
}: {
  reading: NonNullable<InsightV3["field_reading"]>;
  mode: "coach" | "parent";
}) {
  const showExpectedVsReal =
    mode === "coach" &&
    reading.expected_position !== null &&
    reading.actual_position !== null;

  return (
    <section
      aria-label="Lectura del pelotón"
      data-testid="insight-v3-field-reading"
      className="rounded-xl bg-white p-3 ring-1 ring-light-gray"
    >
      <h4 className="text-xs font-medium uppercase tracking-wide text-mid-gray">
        Lectura del pelotón
      </h4>
      <p className="mt-1 text-sm text-charcoal">{reading.summary}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary">{reading.series_label}</Badge>
        {reading.percentile !== null && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Badge variant="info" data-testid="insight-v3-percentile-chip">
                    Percentil {Math.round(reading.percentile)}
                  </Badge>
                </span>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-56">
                100 = ganador de la carrera. A mayor percentil, mejor posición
                relativa dentro del pelotón.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {showExpectedVsReal && (
          <Badge
            variant={deltaSemantics(reading.delta_vs_expected ?? 0).variant}
            data-testid="insight-v3-delta-chip"
          >
            {deltaSemantics(reading.delta_vs_expected ?? 0).label}
          </Badge>
        )}
        {reading.gap_to_p3_hhmmss && (
          <Badge variant="outline" className="gap-1">
            <Activity size={11} aria-hidden="true" />
            {reading.gap_to_p3_hhmmss} a P3
          </Badge>
        )}
      </div>
    </section>
  );
}
