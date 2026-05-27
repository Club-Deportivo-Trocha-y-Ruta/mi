/**
 * CompetitionImportPage — página contenedora del wizard de importación.
 *
 * Rutas:
 *   /competitions/:id/import  → importar para una válida existente
 *   /competitions/import      → crear nueva válida + ingestar (ingest-first)
 *
 * Post-commit: redirige a /competitions/{race_event_id}?tab=results con toast.
 */
import { lazy, Suspense } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
      className="rounded-xl bg-white p-5 ring-1 ring-light-gray"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-mid-gray">
        <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        Cargando wizard…
      </div>
    </div>
  );
}

export function CompetitionImportPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const raceEventId = id ? Number(id) : null;
  const hasExistingEvent = raceEventId != null && !Number.isNaN(raceEventId);

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
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Importar resultados
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          {hasExistingEvent
            ? "Carga el PDF oficial de resultados para esta válida."
            : "Carga el PDF oficial y crea el registro de la válida al mismo tiempo."}
        </p>
      </header>

      {/* ── Wizard ──────────────────────────────────────────────────── */}
      <Suspense fallback={<WizardSkeleton />}>
        <ImportWizard onCompleted={handleCompleted} />
      </Suspense>
    </div>
  );
}
