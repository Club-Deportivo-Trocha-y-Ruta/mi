/**
 * AthleteProgressPage — vista de progreso de fuerza y acondicionamiento de UN
 * deportista (US4 / T037).
 *
 * Ruta: /strength/athletes/:athleteId/progress (coach/admin only — RBAC en
 * App.tsx + backend).
 *
 * Criterios de aceptación:
 *  - Coach/admin únicamente (gating en App.tsx vía ProtectedRoute).
 *  - Usa `useAthleteStrengthProgress` (via `ProgressNotesBoard`).
 *  - Caso 404 "sin registro" manejado con gracia: mensaje claro en lugar de
 *    pantalla de error.
 *  - `ProgressNotesBoard` cargado con React.lazy para no penalizar el bundle.
 *  - Estados de carga / error / servidor-iniciando en toda superficie asíncrona.
 *  - Responsive mobile-first; touch targets ≥ 48 × 48 px.
 *  - WCAG 2.1 AA.
 *  - FR-015: la página se ancla a un ÚNICO `athleteId` tomado del parámetro de
 *    ruta — nunca renderiza ni compone datos de más de un atleta a la vez.
 */
import { lazy, Suspense } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";

// ProgressNotesBoard es pesado (formulario + tabla) → lazy-load.
const ProgressNotesBoard = lazy(() =>
  import("@/components/strength/ProgressNotesBoard").then((m) => ({
    default: m.ProgressNotesBoard,
  })),
);

// ---------------------------------------------------------------------------
// Skeleton de suspense mientras carga el chunk lazy
// ---------------------------------------------------------------------------

function BoardSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando tablero de progreso de fuerza…"
      className="space-y-4"
    >
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-5 w-24 rounded-full" />
          </div>
        ))}
      </div>
      <Skeleton className="h-36 w-full rounded-xl" />
      <Skeleton className="h-28 w-full rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export function AthleteProgressPage() {
  const { athleteId: rawId } = useParams<{ athleteId: string }>();
  const athleteId = Number(rawId) || 0;

  // ── ID inválido ─────────────────────────────────────────────────────────
  if (athleteId <= 0) {
    return (
      <PageShell athleteId={null}>
        <div
          role="alert"
          className="rounded-xl border border-amber-200 bg-amber-50 p-5"
        >
          <p className="text-sm font-semibold text-amber-800">
            El identificador del deportista no es válido.
          </p>
          <p className="mt-1 text-xs text-amber-700">
            Verifica la URL e intenta de nuevo.
          </p>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell athleteId={athleteId}>
      <Suspense fallback={<BoardSkeleton />}>
        <ProgressNotesBoard athleteId={athleteId} />
      </Suspense>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// PageShell — envoltorio con encabezado y navegación
// ---------------------------------------------------------------------------

interface PageShellProps {
  athleteId: number | null;
  children: React.ReactNode;
}

function PageShell({ athleteId, children }: PageShellProps) {
  const backHref =
    athleteId !== null ? `/athletes/${athleteId}` : "/athletes";

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      {/* Navegación: volver al perfil del atleta */}
      <Link
        to={backHref}
        className="mb-5 inline-flex min-h-10 items-center gap-1.5 py-2 text-sm text-slate-500 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
        aria-label="Volver al perfil del deportista"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        Perfil del deportista
      </Link>

      {/* Encabezado de la página */}
      <h1 className="mb-1 text-2xl font-semibold text-slate-900">
        Progreso de fuerza y acondicionamiento
      </h1>
      <p className="mb-6 text-sm text-slate-500">
        Seguimiento individual del proceso de fuerza y acondicionamiento del
        deportista. El avance se registra por esfuerzo y ejecución técnica, y
        no se compara con otros atletas.
      </p>

      {children}
    </div>
  );
}

export default AthleteProgressPage;
