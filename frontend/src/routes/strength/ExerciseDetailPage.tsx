/**
 * ExerciseDetailPage — vista de detalle de un ejercicio de fuerza y
 * acondicionamiento (feature 021 / T017, US1).
 *
 * Ruta: /strength/exercises/:id (coach/admin only — RBAC en App.tsx + backend).
 *
 * Muestra: equipo requerido (con detalle si aplica), categoría de movimiento,
 * franja(s) de edad, duración/repeticiones sugeridas, how_to ("Cómo
 * realizarlo"), errores comunes de ejecución y la figura ilustrativa
 * (ExerciseIllustration — ASCII, FR-006).
 *
 * Estados: cargando (skeleton), error (mensaje + botón reintentar, 404 sin
 * reintentar), id inválido. Responsive mobile-first, WCAG 2.1 AA (headings
 * semánticos, secciones con aria-label, touch targets ≥ 48×48 px).
 * Mirror de `routes/technique/ExerciseDetailPage.tsx`.
 */

import { useParams, Link } from "react-router-dom";
import { ArrowLeft, AlertTriangle, RefreshCw } from "lucide-react";

import { ExerciseIllustration } from "@/components/strength/ExerciseIllustration";
import {
  EQUIPMENT_LABEL,
  MOVEMENT_CATEGORY_LABEL,
  STRENGTH_AGE_BAND_LABEL,
} from "@/components/strength/ExerciseCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { mapStrengthError } from "@/api/strength";
import { useStrengthExercise } from "@/hooks/strength/useStrength";

// ---------------------------------------------------------------------------
// Sub-componentes de skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando ejercicio…"
      className="space-y-4"
    >
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
 * Página de detalle de un ejercicio de fuerza.
 * Parámetro de ruta: id (string → parseado a number).
 */
export function ExerciseDetailPage() {
  const { id: rawId } = useParams<{ id: string }>();
  const exerciseId = Number(rawId) || 0;

  const { data, isLoading, isError, error, refetch } = useStrengthExercise(
    exerciseId,
    exerciseId > 0,
  );

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
    const info = mapStrengthError(error);
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
    equipment,
    equipment_detail,
    movement_category,
    age_bands,
    suggested_duration_min,
    suggested_reps,
    how_to,
    common_errors,
    illustration_ascii,
    illustration_alt,
  } = data;

  return (
    <PageShell>
      {/* ── Encabezado ──────────────────────────────────────────────── */}
      <div className="mb-5 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold text-slate-900 sm:text-2xl">
            {name}
          </h1>
          <Badge
            variant={equipment === "sin_equipo" ? "success" : "info"}
            aria-label="Equipo requerido"
          >
            {EQUIPMENT_LABEL[equipment]}
          </Badge>
        </div>
        {summary && <p className="text-sm text-slate-500">{summary}</p>}
      </div>

      {/* ── Metadatos: categoría, franjas de edad, equipo, dosis sugerida ── */}
      <Card className="mb-5">
        <CardContent className="grid gap-4 pt-4 sm:grid-cols-2">
          {/* Categoría de movimiento */}
          <section aria-label="Categoría de movimiento">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Categoría de movimiento
            </p>
            <Badge variant="outline">
              {MOVEMENT_CATEGORY_LABEL[movement_category]}
            </Badge>
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
                    {STRENGTH_AGE_BAND_LABEL[band]} años
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">Sin franja registrada</p>
            )}
          </section>

          {/* Detalle de equipo (si aplica) */}
          <section aria-label="Detalle del equipo">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Detalle del equipo
            </p>
            <p className="text-sm text-slate-700">
              {equipment_detail?.trim() || "Sin equipo"}
            </p>
          </section>

          {/* Dosis sugerida */}
          <section aria-label="Duración y repeticiones sugeridas">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Dosis sugerida
            </p>
            <p className="text-sm text-slate-700">
              {suggested_duration_min} min · {suggested_reps}
            </p>
          </section>
        </CardContent>
      </Card>

      {/* ── Instrucciones (how_to / "Cómo realizarlo") ──────────────────── */}
      <Card className="mb-5">
        <CardHeader>
          <h2 className="text-base font-semibold text-charcoal">
            Cómo realizarlo
          </h2>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
            {how_to}
          </p>
        </CardContent>
      </Card>

      {/* ── Errores comunes de ejecución ────────────────────────────────── */}
      {common_errors?.trim() && (
        <Card className="mb-5">
          <CardHeader>
            <h2 className="text-base font-semibold text-charcoal">
              Errores comunes
            </h2>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
              {common_errors}
            </p>
          </CardContent>
        </Card>
      )}

      {/* ── Figura ilustrativa (ASCII original, FR-006) ─────────────────── */}
      {illustration_ascii?.trim() && (
        <ExerciseIllustration
          illustration_ascii={illustration_ascii}
          illustration_alt={illustration_alt ?? ""}
        />
      )}
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
        to="/strength"
        className="mb-5 inline-flex items-center gap-1.5 py-3 text-sm text-slate-500 hover:text-slate-800"
        aria-label="Volver al catálogo de ejercicios de fuerza"
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
        <span className="text-sm font-semibold">
          No se pudo cargar el ejercicio
        </span>
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
