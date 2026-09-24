/**
 * CarrerasTab — pestaña única «Carreras» del perfil del atleta (feature 045,
 * US1/US4). Reemplaza a las pestañas «Insights IA» y «Carreras» anteriores,
 * tanto para el coach como para la familia.
 *
 * Props públicas:
 *   - `athlete`   — atleta cargado por la página (`AthleteOut`). `athlete.id`
 *                   es el id que usan todas las vistas.
 *   - `audience`  — `"coach"` | `"family"`. La familia nunca ve «Comparar» ni
 *                   las métricas contra el líder/podio (solo mediana,
 *                   percentil y posición); el coach ve todo.
 *   - `className` — clases extra del contenedor (opcional).
 *
 * Estado en la URL (la pestaña NO toca `tab`; la página dueña lo conserva):
 *   - `view=progresion|analisis|comparar` — vista activa. Ausente o
 *     desconocida → `progresion`. `comparar` es solo-coach: para la familia
 *     cae en `progresion` (nunca es un error).
 *   - `insight=<id>` — abre «Análisis IA» y expande ese análisis (fuerza
 *     `view=analisis`).
 *
 * Rendimiento (constitución IV): cada vista es su propio chunk `React.lazy`
 * y solo se monta la activa — la primera pintura dispara únicamente la
 * consulta de la vista de Progresión (el historial).
 *
 * Los alias de pestaña antiguos (`ai_analysis`, `ai-analysis`) los resuelve
 * la página dueña — esta pestaña solo lee `view`/`insight`.
 */
import { lazy, Suspense, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { BarChart3, Sparkles, TrendingUp } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { AthleteOut } from "@/types/athlete.types";

const ProgressionView = lazy(() =>
  import("@/components/athletes/races/ProgressionView").then((m) => ({
    default: m.ProgressionView,
  })),
);
const AnalysisView = lazy(() =>
  import("@/components/athletes/races/AnalysisView").then((m) => ({
    default: m.AnalysisView,
  })),
);
const CompareView = lazy(() =>
  import("@/components/athletes/races/CompareView").then((m) => ({
    default: m.CompareView,
  })),
);

export type CarrerasAudience = "coach" | "family";
export type CarrerasView = "progresion" | "analisis" | "comparar";

const VIEWS: readonly CarrerasView[] = ["progresion", "analisis", "comparar"];

export interface CarrerasTabProps {
  athlete: AthleteOut;
  audience: CarrerasAudience;
  className?: string;
}

/**
 * Resuelve la vista efectiva a partir de la URL. `insight` fuerza
 * `analisis`; `comparar` cae en `progresion` para la familia.
 */
export function resolveCarrerasView(
  rawView: string | null,
  insightParam: string | null,
  audience: CarrerasAudience,
): CarrerasView {
  if (insightParam) return "analisis";
  const view = VIEWS.find((v) => v === rawView) ?? "progresion";
  if (view === "comparar" && audience !== "coach") return "progresion";
  return view;
}

/** `insight=<id>` → número positivo o `null` (valores inválidos se ignoran). */
export function parseInsightParam(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

function ViewSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando vista"
      className="space-y-3 rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline"
    >
      <Skeleton className="h-5 w-48" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-64 w-full rounded-lg" />
    </div>
  );
}

export function CarrerasTab({ athlete, audience, className }: CarrerasTabProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  const insightParam = searchParams.get("insight");
  const insightId = parseInsightParam(insightParam);
  const view = resolveCarrerasView(
    searchParams.get("view"),
    insightId !== null ? insightParam : null,
    audience,
  );

  const changeView = useCallback(
    (next: string) => {
      const target = VIEWS.find((v) => v === next);
      if (!target || target === view) return;
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          params.set("view", target);
          // Cambiar de vista suelta el análisis expandido: `insight` solo
          // tiene sentido dentro de «Análisis IA».
          params.delete("insight");
          return params;
        },
        { replace: true },
      );
    },
    [setSearchParams, view],
  );

  // Abrir/cerrar un análisis dentro de «Análisis IA» se refleja en `insight=`
  // (enlace compartible). `view=analisis` se fija SIEMPRE: `insight` fuerza
  // esa vista, así que al cerrar el análisis no se debe volver a `progresion`.
  const changeInsight = useCallback(
    (id: number | null) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          params.set("view", "analisis");
          if (id === null) params.delete("insight");
          else params.set("insight", String(id));
          return params;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const triggerClass = "min-h-12 shrink-0 gap-1.5";

  return (
    <section
      className={cn("space-y-4", className)}
      data-testid="carreras-tab"
      aria-label="Carreras"
    >
      <Tabs value={view} onValueChange={changeView} className="w-full">
        <TabsList
          className="flex h-auto w-full flex-wrap justify-start gap-1 bg-light-gray p-1"
          aria-label="Vistas de Carreras"
        >
          <TabsTrigger
            value="progresion"
            className={triggerClass}
            data-testid="carreras-view-progresion"
          >
            <TrendingUp size={14} aria-hidden="true" />
            Progresión
          </TabsTrigger>
          <TabsTrigger
            value="analisis"
            className={triggerClass}
            data-testid="carreras-view-analisis"
          >
            <Sparkles size={14} aria-hidden="true" />
            Análisis IA
          </TabsTrigger>
          {audience === "coach" && (
            <TabsTrigger
              value="comparar"
              className={triggerClass}
              data-testid="carreras-view-comparar"
            >
              <BarChart3 size={14} aria-hidden="true" />
              Comparar
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="progresion" className="mt-4">
          <Suspense fallback={<ViewSkeleton />}>
            <ProgressionView athleteId={athlete.id} audience={audience} />
          </Suspense>
        </TabsContent>
        <TabsContent value="analisis" className="mt-4">
          <Suspense fallback={<ViewSkeleton />}>
            <AnalysisView
              athlete={athlete}
              audience={audience}
              insightId={insightId}
              onInsightChange={changeInsight}
            />
          </Suspense>
        </TabsContent>
        {audience === "coach" && (
          <TabsContent value="comparar" className="mt-4">
            <Suspense fallback={<ViewSkeleton />}>
              <CompareView athleteId={athlete.id} />
            </Suspense>
          </TabsContent>
        )}
      </Tabs>
    </section>
  );
}
