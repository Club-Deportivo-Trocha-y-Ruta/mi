/**
 * ExerciseDetailPage — vista de detalle de un ejercicio técnico / gymkhana.
 *
 * Ruta: /technique/exercises/:id (coach/admin only — RBAC en App.tsx + backend).
 *
 * Criterios de aceptación (T022):
 *  - Muestra: habilidad(es), franja(s) de edad, dificultad, materiales
 *    (con texto claro "Sin material" cuando is_none=true), how_to / "Cómo
 *    realizarlo", y el componente CircuitLayout (si es gymkhana).
 *  - Estados diseñados: cargando (skeleton), error (mensaje + botón reintentar),
 *    cold-start Render ("servidor iniciando" vía ServerWakingBanner global —
 *    ya montado en el layout; aquí no duplicamos), 404 (ejercicio no encontrado).
 *  - Responsive mobile-first; touch targets ≥ 48×48 px.
 *  - WCAG 2.1 AA: headings semánticos, badges con texto legible, secciones
 *    con aria-label.
 */

import { useParams, Link } from "react-router-dom";
import { ArrowLeft, AlertTriangle, RefreshCw } from "lucide-react";

import { CircuitLayout } from "@/components/technique/CircuitLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { mapTechniqueError } from "@/api/technique";
import { useTechniqueExercise } from "@/hooks/technique/useTechnique";
import type { Difficulty, AgeBand } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Helpers de presentación
// ---------------------------------------------------------------------------

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  facil: "Fácil",
  media: "Media",
  avanzada: "Avanzada",
};

const DIFFICULTY_VARIANT: Record<
  Difficulty,
  "success" | "warning" | "destructive"
> = {
  facil: "success",
  media: "warning",
  avanzada: "destructive",
};

const AGE_BAND_LABELS: Record<AgeBand, string> = {
  "7-9": "7-9 años",
  "10-12": "10-12 años",
  "13-15": "13-15 años",
};

// ---------------------------------------------------------------------------
// Sub-componentes de skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando ejercicio…" className="space-y-4">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-4/5" />
      <div className="mt-4 flex gap-2">
        <Skeleton className="h-6 w-20 rounded-full" />
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>
      <Skeleton className="mt-4 h-32 w-full rounded-xl" />
      <Skeleton className="h-24 w-full rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

/**
 * Página de detalle de un ejercicio técnico.
 * Parámetro de ruta: id (string → parseado a number).
 */
export function ExerciseDetailPage() {
  const { id: rawId } = useParams<{ id: string }>();
  const exerciseId = Number(rawId) || 0;

  const { data, isLoading, isError, error, refetch } =
    useTechniqueExercise(exerciseId, exerciseId > 0);

  // ── Estado: id inválido ─────────────────────────────────────────────────
  if (exerciseId <= 0) {
    return (
      <PageShell>
        <ErrorState message="El identificador del ejercicio no es válido." />
      </PageShell>
    );
  }

  // ── Estado: cargando ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <PageShell>
        <DetailSkeleton />
      </PageShell>
    );
  }

  // ── Estado: error ───────────────────────────────────────────────────────
  if (isError || !data) {
    const info = mapTechniqueError(error);
    const is404 = info.kind === "not_found";
    return (
      <PageShell>
        <ErrorState
          message={
            is404
              ? "No se encontró este ejercicio o fue eliminado."
              : info.message
          }
          onRetry={is404 ? undefined : () => void refetch()}
        />
      </PageShell>
    );
  }

  // ── Estado: datos disponibles ───────────────────────────────────────────
  const {
    name,
    summary,
    difficulty,
    is_game,
    is_gymkhana,
    age_bands,
    skills,
    materials,
    how_to,
  } = data;

  const noMaterialMats = materials.filter((m) => m.is_none);
  const realMats = materials.filter((m) => !m.is_none);
  const hasMaterials = realMats.length > 0;

  return (
    <PageShell>
      {/* ── Encabezado ──────────────────────────────────────────────── */}
      <div className="mb-5 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold text-slate-900 sm:text-2xl">
            {name}
          </h1>
          {is_game && (
            <Badge variant="info" aria-label="Ejercicio de juego / engagement">
              Juego
            </Badge>
          )}
          {is_gymkhana && (
            <Badge variant="secondary" aria-label="Ejercicio de gymkhana">
              Gymkhana
            </Badge>
          )}
        </div>
        {summary && (
          <p className="text-sm text-slate-500">{summary}</p>
        )}
      </div>

      {/* ── Metadatos: habilidades, franjas de edad, dificultad, materiales ── */}
      <Card className="mb-5">
        <CardContent className="grid gap-4 pt-4 sm:grid-cols-2">
          {/* Habilidades */}
          <section aria-label="Habilidades técnicas">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Habilidades técnicas
            </p>
            {skills.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {skills.map((skill) => (
                  <Badge key={skill.code} variant="outline">
                    {skill.name}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">Sin habilidades registradas</p>
            )}
          </section>

          {/* Franjas de edad */}
          <section aria-label="Franjas de edad">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Franjas de edad
            </p>
            {age_bands.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {age_bands.map((band) => (
                  <Badge key={band} variant="secondary">
                    {AGE_BAND_LABELS[band]}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">Sin franja registrada</p>
            )}
          </section>

          {/* Dificultad */}
          <section aria-label="Nivel de dificultad">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Dificultad
            </p>
            <Badge variant={DIFFICULTY_VARIANT[difficulty]}>
              {DIFFICULTY_LABELS[difficulty]}
            </Badge>
          </section>

          {/* Materiales */}
          <section aria-label="Materiales necesarios">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Materiales
            </p>
            {/* Cuando hay materiales reales, los mostramos */}
            {hasMaterials && (
              <div className="flex flex-wrap gap-1.5">
                {realMats.map((mat) => (
                  <Badge key={mat.slug} variant="outline">
                    {mat.name}
                  </Badge>
                ))}
              </div>
            )}
            {/* Indicador explícito de "sin material" (FR-009) */}
            {(noMaterialMats.length > 0 || !hasMaterials) && (
              <p className="text-sm font-medium text-slate-500">
                Sin material
              </p>
            )}
          </section>
        </CardContent>
      </Card>

      {/* ── Instrucciones (how_to / "Cómo realizarlo") ──────────────────── */}
      <Card className="mb-5">
        <CardHeader>
          {/* h2 — respeta el orden h1 (nombre ejercicio) → h2 (sección) para WCAG 1.3.1 */}
          <h2 className="text-base font-semibold text-charcoal">Cómo realizarlo</h2>
        </CardHeader>
        <CardContent>
          {/* how_to puede contener saltos de línea; los conservamos */}
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
            {how_to}
          </p>
        </CardContent>
      </Card>

      {/* ── Diagrama del circuito (solo gymkhana con layout_ascii) ──────── */}
      <CircuitLayout exercise={data} />
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Componentes auxiliares de layout
// ---------------------------------------------------------------------------

/** Envoltorio con ancho máximo, padding y enlace "Volver". */
function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <Link
        to="/technique"
        className="mb-5 inline-flex items-center gap-1.5 py-3 text-sm text-slate-500 hover:text-slate-800"
        aria-label="Volver al catálogo de ejercicios"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        Catálogo
      </Link>
      {children}
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

/** Estado de error con mensaje amigable y botón opcional de reintento. */
function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-5"
    >
      <div className="flex items-center gap-2 text-red-700">
        <AlertTriangle size={18} aria-hidden="true" />
        <span className="text-sm font-semibold">No se pudo cargar el ejercicio</span>
      </div>
      <p className="text-sm text-red-600">{message}</p>
      {onRetry && (
        <Button
          variant="outline"
          onClick={onRetry}
          className="min-h-12 gap-1.5"
        >
          <RefreshCw size={14} aria-hidden="true" />
          Reintentar
        </Button>
      )}
    </div>
  );
}

export default ExerciseDetailPage;
