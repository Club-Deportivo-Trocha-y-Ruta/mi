/**
 * Línea de tiempo de insights aprobados del atleta (FE-1).
 *
 * - Lista cards por insight (más recientes primero).
 * - Click en card abre Sheet (mobile) o Dialog (md+) con el detalle
 *   completo (markdown rehidratado, recommendations, snapshot, cadena
 *   ``supersedes``).
 * - El layout responsive se decide al runtime con ``matchMedia`` para
 *   evitar duplicar todo el árbol en SSR-style "hidden md:block".
 *
 * v2 (Task #8):
 *   - Preview: si prompt_version === "race_analyst_v2", muestra primera
 *     línea del bloque "## Qué pasó". Legacy v1 muestra truncate del
 *     summary_text completo.
 *   - Detalle: si v2, renderiza 4 secciones collapsibles (details).
 *     Legacy v1 mantiene MarkdownReportViewer.
 *
 * Privacidad: el backend ya filtra el listado según el rol. Acá no
 * se hace nada adicional — confiamos en BE-2.
 *
 * Accesibilidad:
 *   - Cada card es un ``<button>`` con ``aria-label`` legible.
 *   - El detalle abre como modal con foco trapado (Radix lo da).
 *   - El estado de loading expone ``role="status" aria-busy``.
 */
import { useEffect, useState } from "react";
import { ChevronRight, History, Sparkles } from "lucide-react";

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
import { cn } from "@/lib/utils";
import type {
  AthleteInsightOut,
  InsightConfidence,
  InsightLink,
  InsightParsedSections,
} from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Helpers de parsing para insights v2
// ---------------------------------------------------------------------------

const PROMPT_VERSION_V2 = "race_analyst_v2";

/** Normaliza acentos y casing para comparar headers tolerando variantes. */
function normalizeHeader(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/**
 * Extrae el contenido de una sección markdown delimitada por un header ##.
 * Devuelve el texto entre el header encontrado y el siguiente header ## (o
 * fin de string).
 *
 * Usa `startsWith` sobre el header normalizado para tolerar variantes del
 * backend (ej: "## Qué pasó en esta válida" matchea con headerText "Qué pasó",
 * "## Recorrido hasta acá" matchea con "Recorrido hasta").
 */
function extractSection(markdown: string, headerText: string): string {
  const lines = markdown.split("\n");
  const needle = normalizeHeader(headerText);
  let inside = false;
  const collected: string[] = [];
  for (const line of lines) {
    if (/^##\s/.test(line)) {
      if (inside) break;
      const headerInLine = normalizeHeader(line.replace(/^##\s+/, ""));
      if (headerInLine.startsWith(needle)) {
        inside = true;
        continue;
      }
    } else if (inside) {
      collected.push(line);
    }
  }
  return collected.join("\n").trim();
}

/**
 * Parsea las 4 secciones del summary_text de un insight v2.
 * Los headers en el markdown son exactamente:
 *   ## Qué pasó / ## Recorrido hasta aquí / ## Hacia dónde va / ## Resumen de temporada
 */
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

/**
 * Para la preview de la card, extrae la primera línea no vacía del bloque
 * "Qué pasó" en insights v2.
 */
function getV2Preview(summaryText: string): string {
  const section = extractSection(summaryText, "Qué pasó");
  if (!section) return summaryText;
  const firstLine = section
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.length > 0);
  return firstLine ?? summaryText;
}

const SUMMARY_MAX_CHARS = 160;

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

function confidenceVariant(
  confidence: InsightConfidence,
): "success" | "warning" | "destructive" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  return "destructive";
}

function confidenceLabel(confidence: InsightConfidence): string {
  if (confidence === "high") return "Confianza alta";
  if (confidence === "medium") return "Confianza media";
  return "Confianza baja";
}

function validaLabel(valida: number | null | undefined): string {
  if (valida === null || valida === undefined) return "—";
  if (valida === 0) return "Resumen de temporada";
  if (valida === 99) return "Cto. Departamental";
  return `Válida ${valida}`;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}


interface InsightsTimelineProps {
  athleteId: number;
  mode: "coach" | "parent";
}

/** Hook utilitario: ``true`` si la ventana cumple media query, ``false``
 * en SSR/tests donde matchMedia no existe. Re-evalúa en resize. */
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
    // Compat: navegadores viejos usan addListener/removeListener.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", handler);
      return () => mql.removeEventListener("change", handler);
    }
    mql.addListener(handler);
    return () => mql.removeListener(handler);
  }, [query]);

  return matches;
}

export function InsightsTimeline({ athleteId, mode }: InsightsTimelineProps) {
  const insightsQuery = useAthleteInsights(athleteId, {
    latest_only: true,
    limit: 50,
  });

  const [selectedInsightId, setSelectedInsightId] = useState<number | null>(null);
  const isDesktop = useMediaQuery("(min-width: 768px)");

  const items: AthleteInsightOut[] = insightsQuery.data?.items ?? [];

  // ---- Loading state ----------------------------------------------------
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

  // ---- Error state ------------------------------------------------------
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

  // ---- Empty state ------------------------------------------------------
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
            ? "Lanza un análisis desde la pestaña “Lanzar” para crear el primero."
            : "Cuando tu entrenador apruebe un análisis, lo verás aquí."}
        </p>
      </div>
    );
  }

  // ---- List ------------------------------------------------------------
  return (
    <>
      <ul className="space-y-3" aria-label="Histórico de análisis del deportista">
        {items.map((insight) => (
          <li key={insight.id}>
            <button
              type="button"
              onClick={() => setSelectedInsightId(insight.id)}
              data-testid={`insight-card-${insight.id}`}
              aria-label={`Ver análisis del ${formatDateTimeCompact(insight.generated_at)}, ${validaLabel(insight.valida_num)}, ${confidenceLabel(insight.confidence)}`}
              className={cn(
                "group flex w-full items-start gap-3 rounded-xl bg-white p-4 text-left transition-colors",
                "hover:bg-light-gray/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
              )}
              style={{ boxShadow: cardShadow }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                    {formatDateTimeCompact(insight.generated_at)}
                  </span>
                  <Badge variant="secondary">{validaLabel(insight.valida_num)}</Badge>
                  <Badge variant={confidenceVariant(insight.confidence)}>
                    {confidenceLabel(insight.confidence)}
                  </Badge>
                  {!insight.is_active && (
                    <Badge variant="outline">Histórico</Badge>
                  )}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-charcoal">
                  {insight.prompt_version === PROMPT_VERSION_V2
                    ? truncate(getV2Preview(insight.summary_text), SUMMARY_MAX_CHARS)
                    : truncate(insight.summary_text, SUMMARY_MAX_CHARS)}
                </p>
              </div>
              <ChevronRight
                size={18}
                className="mt-1 shrink-0 text-mid-gray transition-transform group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </button>
          </li>
        ))}
      </ul>

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
// Secciones v2 — renderiza los 4 bloques del prompt race_analyst_v2
// ---------------------------------------------------------------------------

/** Labels por sección para coach y para parent. */
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
        // Primera sección abierta por defecto
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
// Versiones anteriores — accordion HTML nativo (<details>) para no
// agregar dependencias.
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
