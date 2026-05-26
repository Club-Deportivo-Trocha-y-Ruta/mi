/**
 * Línea de tiempo de insights aprobados del atleta (FE-1).
 *
 * Sprint 2 (BB1 + BB4):
 *   - Agrupación por mes-año con header sticky y badge de carrera tier.
 *   - Shape diferenciado por tipo: resumen-temporada (borde primary + Trophy),
 *     Cto. Departamental (borde amber + Medal), válida normal (compacto).
 *   - Checkbox multi-select solo para coach (BB4).
 *   - Click en card abre Sheet (mobile) o Dialog (md+) con detalle completo.
 *
 * Privacidad: el backend ya filtra el listado según el rol. El checkbox de
 * multi-select NUNCA se renderiza para mode="parent".
 *
 * Accesibilidad:
 *   - Cada card es un ``<button>`` con ``aria-label`` legible.
 *   - El detalle abre como modal con foco trapado (Radix lo da).
 *   - El estado de loading expone ``role="status" aria-busy``.
 */
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, History, Medal, Sparkles, Trophy } from "lucide-react";

import { MarkdownReportViewer } from "@/components/ai/MarkdownReportViewer";
import { InsightN1Banner } from "./InsightN1Banner";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteInsightDetail } from "@/hooks/athletes/useAthleteInsightDetail";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  extractSection,
  getCarreraTier,
  getV2Preview,
  PROMPT_VERSION_V2,
  validaLabel,
} from "@/lib/insights";
import { cn } from "@/lib/utils";
import type {
  AthleteInsightOut,
  InsightLink,
  InsightParsedSections,
} from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Helpers locales — parsing v2 (parseV2Sections usa extractSection de lib)
// ---------------------------------------------------------------------------

function parseV2Sections(summaryText: string): InsightParsedSections {
  return {
    what_happened: extractSection(summaryText, "Qué pasó") || undefined,
    journey_so_far:
      extractSection(summaryText, "Recorrido hasta") || undefined,
    looking_ahead: extractSection(summaryText, "Hacia dónde va") || undefined,
    season_summary:
      extractSection(summaryText, "Resumen de temporada") || undefined,
  };
}

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface InsightsTimelineProps {
  athleteId: number;
  mode: "coach" | "parent";
  /** Controlado desde el padre para abrir el drawer via PanoramaView. */
  selectedInsightId?: number | null;
  /** Callback para levantar el estado al padre cuando cambia la selección. */
  onSelectInsight?: (id: number | null) => void;
  /** IDs actualmente seleccionados para boletín (BB4). Solo coach. */
  newsletterSelection?: Set<number>;
  /** Toggle del checkbox de boletín (BB4). Solo coach. */
  onToggleSelection?: (id: number) => void;
}

// ---------------------------------------------------------------------------
// Utilidad: matchMedia hook
// ---------------------------------------------------------------------------

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handler);
      return () => mql.removeEventListener("change", handler);
    }
    mql.addListener(handler);
    return () => mql.removeListener(handler);
  }, [query]);

  return matches;
}

// ---------------------------------------------------------------------------
// Helpers de UI por tipo de insight
// ---------------------------------------------------------------------------

type InsightShape = "season-summary" | "departamental" | "normal";

function resolveShape(validaNum: number | null | undefined): InsightShape {
  if (validaNum === 0) return "season-summary";
  if (validaNum === 99) return "departamental";
  return "normal";
}

/** Badge del tier de carrera Copa Valle (A / B / C / CD). */
function CarreraTierBadge({ tier }: { tier: "A" | "B" | "C" | "CD" }) {
  return (
    <Badge
      variant="outline"
      className="text-[10px] shrink-0"
      aria-label={`Tipo de carrera: ${tier}`}
    >
      Carrera {tier}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function InsightsTimeline({
  athleteId,
  mode,
  selectedInsightId: controlledInsightId,
  onSelectInsight,
  newsletterSelection,
  onToggleSelection,
}: InsightsTimelineProps) {
  const insightsQuery = useAthleteInsights(athleteId, {
    latest_only: true,
    limit: 50,
  });

  const [localInsightId, setLocalInsightId] = useState<number | null>(null);
  const selectedInsightId = controlledInsightId ?? localInsightId;
  const setSelectedInsightId = (id: number | null) => {
    setLocalInsightId(id);
    onSelectInsight?.(id);
  };
  const isDesktop = useMediaQuery("(min-width: 768px)");

  const items: AthleteInsightOut[] = insightsQuery.data?.items ?? [];

  // ---- Agrupación por mes-año (BB1) ----------------------------------------
  const grouped = useMemo(() => {
    const map = new Map<string, AthleteInsightOut[]>();
    items.forEach((i) => {
      const d = new Date(i.generated_at);
      const key = new Intl.DateTimeFormat("es-CO", {
        month: "long",
        year: "numeric",
      }).format(d);
      const arr = map.get(key) ?? [];
      arr.push(i);
      map.set(key, arr);
    });
    return Array.from(map.entries());
  }, [items]);

  // ---- Loading state -------------------------------------------------------
  if (insightsQuery.isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando histórico de análisis"
        className="space-y-3"
      >
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  // ---- Error state ---------------------------------------------------------
  if (insightsQuery.isError) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
      >
        <p className="font-semibold">No pudimos cargar el histórico</p>
        <p className="mt-1 text-xs">
          {insightsQuery.error instanceof Error
            ? insightsQuery.error.message
            : "Error desconocido al consultar el servidor."}
        </p>
      </div>
    );
  }

  // ---- Empty state ---------------------------------------------------------
  if (items.length === 0) {
    return (
      <div
        className="rounded-xl bg-white p-8 text-center"
        style={{ boxShadow: cardShadow }}
      >
        <Sparkles
          size={28}
          className="mx-auto text-mid-gray"
          aria-hidden="true"
        />
        <p className="mt-3 text-sm font-medium text-charcoal">
          Aún no hay análisis aprobados para este deportista.
        </p>
        <p className="mt-1 text-xs text-mid-gray">
          {mode === "coach"
            ? 'Lanza un análisis desde la pestaña "Lanzar" para crear el primero.'
            : "Cuando tu entrenador apruebe un análisis, lo verás aquí."}
        </p>
      </div>
    );
  }

  // ---- Lista agrupada (BB1) ------------------------------------------------
  return (
    <>
      <div
        className="space-y-0 overflow-hidden rounded-xl"
        aria-label="Histórico de análisis del deportista"
      >
        {grouped.map(([monthKey, groupItems]) => {
          // Tier de carrera basado en la fecha del primer item del grupo.
          // Solo se muestra si NINGUNO de los items es resumen-temporada
          // (valida_num === 0).
          const hasSeasonSummary = groupItems.some((i) => i.valida_num === 0);
          const firstDate = groupItems[0]?.generated_at;
          const tier =
            !hasSeasonSummary && firstDate
              ? getCarreraTier(firstDate)
              : null;

          return (
            <section key={monthKey} className="space-y-2 pb-4">
              {/* Header sticky del grupo */}
              <div className="sticky top-0 z-10 flex items-center gap-2 bg-white/95 px-3 py-2 backdrop-blur-sm">
                <span className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
                  {monthKey}
                </span>
                {tier && <CarreraTierBadge tier={tier} />}
              </div>

              {/* Cards del grupo */}
              <ul className="space-y-2 px-1">
                {groupItems.map((insight) => {
                  const shape = resolveShape(insight.valida_num);
                  const isSelected =
                    newsletterSelection?.has(insight.id) ?? false;

                  return (
                    <li key={insight.id}>
                      <InsightCard
                        insight={insight}
                        shape={shape}
                        mode={mode}
                        isSelected={isSelected}
                        onOpen={() => setSelectedInsightId(insight.id)}
                        onToggleSelection={
                          mode === "coach" ? onToggleSelection : undefined
                        }
                      />
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>

      <InsightDetailDrawer
        athleteId={athleteId}
        insightId={selectedInsightId}
        onClose={() => setSelectedInsightId(null)}
        useDialog={isDesktop}
        mode={mode}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// InsightCard — card individual con shape por tipo + checkbox multi-select
// ---------------------------------------------------------------------------

interface InsightCardProps {
  insight: AthleteInsightOut;
  shape: InsightShape;
  mode: "coach" | "parent";
  isSelected: boolean;
  onOpen: () => void;
  onToggleSelection?: (id: number) => void;
}

function InsightCard({
  insight,
  shape,
  mode,
  isSelected,
  onOpen,
  onToggleSelection,
}: InsightCardProps) {
  const showCheckbox = mode === "coach" && !!onToggleSelection;

  // Borde izquierdo y ícono según tipo
  const borderCls =
    shape === "season-summary"
      ? "border-l-4 border-primary"
      : shape === "departamental"
        ? "border-l-4 border-amber-400"
        : "";

  return (
    <div className="relative flex items-start gap-2">
      {/* Checkbox multi-select (solo coach) — BB4 */}
      {showCheckbox && (
        <div className="flex shrink-0 items-center pt-4 pl-1">
          <input
            type="checkbox"
            id={`insight-checkbox-${insight.id}`}
            data-testid={`insight-checkbox-${insight.id}`}
            checked={isSelected}
            onChange={() => onToggleSelection?.(insight.id)}
            aria-label={`Seleccionar análisis ${validaLabel(insight.valida_num)} para boletín`}
            className="h-4 w-4 cursor-pointer rounded border-mid-gray accent-primary"
          />
        </div>
      )}

      <button
        type="button"
        onClick={onOpen}
        data-testid={`insight-card-${insight.id}`}
        aria-label={`Ver análisis del ${formatDateTimeCompact(insight.generated_at)}, ${validaLabel(insight.valida_num)}`}
        className={cn(
          "group flex w-full items-start gap-3 rounded-xl bg-white p-4 text-left transition-colors",
          "hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
          borderCls,
        )}
        style={{ boxShadow: cardShadow }}
      >
        {/* Ícono según tipo */}
        {shape === "season-summary" && (
          <Trophy
            size={16}
            className="mt-0.5 shrink-0 text-primary"
            aria-hidden="true"
          />
        )}
        {shape === "departamental" && (
          <Medal
            size={16}
            className="mt-0.5 shrink-0 text-amber-500"
            aria-hidden="true"
          />
        )}

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
              {formatDateTimeCompact(insight.generated_at)}
            </span>
            <Badge variant="secondary">{validaLabel(insight.valida_num)}</Badge>
            {!insight.is_active && (
              <Badge variant="outline">Histórico</Badge>
            )}
          </div>
          <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-charcoal">
            {insight.prompt_version === PROMPT_VERSION_V2
              ? getV2Preview(insight.summary_text)
              : insight.summary_text}
          </p>
        </div>
        <ChevronRight
          size={18}
          className="mt-1 shrink-0 text-mid-gray transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail drawer — Sheet (mobile) o Dialog (desktop)
// ---------------------------------------------------------------------------

interface InsightDetailDrawerProps {
  athleteId: number;
  insightId: number | null;
  onClose: () => void;
  useDialog: boolean;
  mode: "coach" | "parent";
}

function InsightDetailDrawer({
  athleteId,
  insightId,
  onClose,
  useDialog,
  mode,
}: InsightDetailDrawerProps) {
  const isOpen = insightId !== null;
  const detailQuery = useAthleteInsightDetail(athleteId, insightId);

  const handleOpenChange = (open: boolean) => {
    if (!open) onClose();
  };

  const body = (() => {
    if (detailQuery.isLoading) {
      return (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando detalle del análisis"
          className="space-y-3"
        >
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-32 w-full" />
        </div>
      );
    }
    if (detailQuery.isError || !detailQuery.data) {
      return (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <p className="font-semibold">No pudimos cargar el detalle</p>
          <p className="mt-1 text-xs">
            {detailQuery.error instanceof Error
              ? detailQuery.error.message
              : "Intenta cerrar y abrir de nuevo."}
          </p>
        </div>
      );
    }
    const insight = detailQuery.data;
    const isV2 = insight.prompt_version === PROMPT_VERSION_V2;
    const sections = isV2 ? parseV2Sections(insight.summary_text) : null;

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{validaLabel(insight.valida_num)}</Badge>
          <Badge variant={confidenceVariant(insight.confidence)}>
            {confidenceLabel(insight.confidence)}
          </Badge>
          {mode === "coach" && (
            <Badge variant="outline">v{insight.prompt_version}</Badge>
          )}
        </div>

        {insight.is_first_in_season === true && <InsightN1Banner mode={mode} />}

        {isV2 && sections ? (
          <InsightV2Sections sections={sections} mode={mode} />
        ) : (
          <MarkdownReportViewer markdown={insight.summary_text} />
        )}

        {insight.recommendations.length > 0 && (
          <section
            aria-label="Recomendaciones"
            className="rounded-xl bg-white p-4 ring-1 ring-light-gray space-y-2"
          >
            <h3
              className="text-sm text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
            >
              Recomendaciones
            </h3>
            <ul className="space-y-2 text-sm text-charcoal">
              {insight.recommendations.map((rec, idx) => {
                const text =
                  typeof rec === "object" && rec !== null && "text" in rec
                    ? String((rec as { text: unknown }).text ?? "")
                    : JSON.stringify(rec);
                return (
                  <li key={idx} className="rounded-lg bg-light-gray/30 px-3 py-2">
                    {text}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {insight.supersedes.length > 0 && (
          <SupersedesSection chain={insight.supersedes} />
        )}
      </div>
    );
  })();

  if (useDialog) {
    return (
      <Dialog open={isOpen} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Detalle del análisis</DialogTitle>
            <DialogDescription>
              Informe generado y aprobado por el entrenador.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] overflow-y-auto">{body}</DialogBody>
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet open={isOpen} onOpenChange={handleOpenChange}>
      <SheetContent side="right" className="sm:max-w-lg w-full">
        <SheetHeader>
          <SheetTitle>Detalle del análisis</SheetTitle>
          <SheetDescription>
            Informe generado y aprobado por el entrenador.
          </SheetDescription>
        </SheetHeader>
        <SheetBody>{body}</SheetBody>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Secciones v2
// ---------------------------------------------------------------------------

const SECTION_LABELS: Record<
  keyof InsightParsedSections,
  { coach: string; parent: string }
> = {
  what_happened: { coach: "Qué pasó", parent: "Qué pasó" },
  journey_so_far: { coach: "Recorrido hasta aquí", parent: "Recorrido" },
  looking_ahead: { coach: "Hacia dónde va", parent: "Hacia dónde va" },
  season_summary: { coach: "Resumen de temporada", parent: "Resumen temporada" },
};

const SECTION_ORDER: Array<keyof InsightParsedSections> = [
  "what_happened",
  "journey_so_far",
  "looking_ahead",
  "season_summary",
];

interface InsightV2SectionsProps {
  sections: InsightParsedSections;
  mode: "coach" | "parent";
}

function InsightV2Sections({ sections, mode }: InsightV2SectionsProps) {
  const visibleSections = SECTION_ORDER.filter((key) => !!sections[key]);

  if (visibleSections.length === 0) {
    return (
      <p className="text-sm text-mid-gray">
        No se encontraron secciones en este análisis.
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid="insight-v2-sections">
      {visibleSections.map((key, index) => {
        const label =
          mode === "parent"
            ? SECTION_LABELS[key].parent
            : SECTION_LABELS[key].coach;
        const content = sections[key] ?? "";
        const isOpen = index === 0;
        return (
          <details
            key={key}
            open={isOpen}
            className="rounded-xl bg-white ring-1 ring-light-gray"
            data-testid={`insight-v2-section-${key}`}
          >
            <summary
              className={cn(
                "flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-charcoal",
                "hover:bg-light-gray/30 rounded-xl transition-colors select-none",
              )}
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif" }}
            >
              {label}
            </summary>
            <div className="px-4 pb-4 pt-1">
              <p className="text-sm leading-relaxed text-charcoal whitespace-pre-wrap">
                {content}
              </p>
            </div>
          </details>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Versiones anteriores
// ---------------------------------------------------------------------------

function SupersedesSection({ chain }: { chain: InsightLink[] }) {
  return (
    <details
      className="rounded-xl bg-white p-4 ring-1 ring-light-gray"
      data-testid="insight-supersedes"
    >
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-charcoal">
        <History size={14} aria-hidden="true" />
        Versiones anteriores ({chain.length})
      </summary>
      <ul className="mt-3 space-y-1.5 text-xs text-mid-gray">
        {chain.map((link) => (
          <li
            key={link.id}
            className="flex items-center justify-between gap-2 rounded-md bg-light-gray/30 px-2.5 py-1.5"
          >
            <span>{formatDateTimeCompact(link.generated_at)}</span>
            <span className="font-mono">#{link.id}</span>
            {link.coach_approved ? (
              <Badge variant="success">Aprobado</Badge>
            ) : (
              <Badge variant="outline">Borrador</Badge>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
