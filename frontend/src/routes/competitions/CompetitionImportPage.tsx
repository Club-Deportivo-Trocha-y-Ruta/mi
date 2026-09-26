/**
 * CompetitionImportPage — página contenedora de la revisión de una carga
 * (amendment 2026-09-26, `contracts/ui-review-only.md`).
 *
 * Rutas: `/competitions/:id/import` y `/competitions/import`.
 *   - Con `?import=<id>`: renderiza el wizard de revisión (el asistente sin
 *     el paso de subida).
 *   - Sin `?import`: la app ya no sube archivos — redirige al tablero
 *     (`/competitions/imports?seccion=cargas`), donde aparecen las cargas
 *     preparadas fuera de la app.
 *
 * Post-commit: redirige a /competitions/{race_event_id}?tab=results con toast.
 */
import { lazy, Suspense } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";

import type { ImportCommitResponse } from "@/types/raceImports.types";

// Carga lazy del wizard — chunk pesado (~18 KB gzip)
const ImportWizard = lazy(() =>
  import("@/components/competitions/import/ImportWizard").then((m) => ({
    default: m.ImportWizard,
  })),
);

function WizardSkeleton() {
  return (
    <div
      className="rounded-xl bg-surface-raised p-5 ring-1 ring-light-gray"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-mid-gray">
        <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        Abriendo la carga…
      </div>
    </div>
  );
}

export function CompetitionImportPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const raceEventId = id ? Number(id) : null;
  const hasExistingEvent = raceEventId != null && !Number.isNaN(raceEventId);

  // Amendment 2026-09-26 — sin `?import=<id>` no hay nada que revisar: la
  // app ya no sube archivos. Redirige al tablero de cargas.
  if (!searchParams.get("import")) {
    return <Navigate to="/competitions/imports?seccion=cargas" replace />;
  }

  function handleCompleted(response: ImportCommitResponse) {
    const targetId = response.race_event_id ?? raceEventId;
    if (targetId) {
      navigate(`/competitions/${targetId}?tab=results`, { replace: true });
    } else {
      navigate("/competitions", { replace: true });
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-6">
      {/* ── Breadcrumb ──────────────────────────────────────────────── */}
      <Link
        to={hasExistingEvent ? `/competitions/${raceEventId}` : "/competitions"}
        className="inline-flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
        data-testid="import-back-link"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        {hasExistingEvent ? "Volver a competencia" : "Volver a competencias"}
      </Link>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <header>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Revisar carga de resultados
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Revisa la lectura, resuelve lo pendiente y confirma.
        </p>
      </header>

      {/* ── Wizard ──────────────────────────────────────────────────── */}
      <Suspense fallback={<WizardSkeleton />}>
        <ImportWizard onCompleted={handleCompleted} />
      </Suspense>
    </div>
  );
}
