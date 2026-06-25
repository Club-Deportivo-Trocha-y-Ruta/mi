/**
 * SessionBuilderPage — página de armado de sesión técnica (US3 / T031).
 *
 * Flujo (<3 min):
 *   1. Carga el catálogo de ejercicios y la lista de atletas.
 *   2. El entrenador elige ejercicios por segmento + datos de sesión.
 *   3. Al guardar llama a useAssembleTechniqueSession (POST /api/technique/sessions).
 *   4. En éxito muestra el banner de confirmación con enlace a la sesión creada
 *      (/training/sessions/:id) y, si aplica, el aviso de franjas mixtas.
 *
 * Estados cubiertos:
 *   - loading catálogo / atletas → skeletons
 *   - error catálogo             → mensaje con variante cold-start
 *   - mutation pending           → botón deshabilitado + texto "Guardando…"
 *   - mutation error             → error inline debajo del botón
 *   - mutation success           → banner de confirmación + enlace
 *
 * Coach/admin only — gating en App.tsx (ProtectedRoute).
 */

import { Link } from "react-router-dom";

import { MixedAgeNotice } from "@/components/technique/MixedAgeNotice";
import { SessionAssembler } from "@/components/technique/SessionAssembler";
import { Skeleton } from "@/components/ui/skeleton";
import { useAssembleTechniqueSession, useTechniqueCatalog } from "@/hooks/technique/useTechnique";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import { mapTechniqueError } from "@/api/technique";
import type { AssembleSessionInput, AssembleSessionResult } from "@/types/technique.types";
import { useState } from "react";

// ---------------------------------------------------------------------------
// Cold-start / error helper (matches CatalogGrid pattern)
// ---------------------------------------------------------------------------

function resolveErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    if (
      msg.includes("timeout") ||
      msg.includes("network") ||
      msg.includes("503") ||
      msg.includes("502")
    ) {
      return "El servidor está iniciando, puede tomar hasta 60 segundos. Intenta de nuevo en un momento.";
    }
  }
  return "No se pudo cargar el catálogo de ejercicios. Intenta de nuevo.";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SessionBuilderPage() {
  const catalog = useTechniqueCatalog();
  const athletes = useAthletes();
  const assemble = useAssembleTechniqueSession();

  const [result, setResult] = useState<AssembleSessionResult | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  function handleSubmit(input: AssembleSessionInput) {
    setMutationError(null);
    setResult(null);
    assemble.mutate(input, {
      onSuccess: (data) => {
        setResult(data);
      },
      onError: (err) => {
        setMutationError(mapTechniqueError(err).message);
      },
    });
  }

  // ── Loading state ──
  const isLoading = catalog.isLoading || athletes.isLoading;

  if (isLoading) {
    return (
      <div
        className="mx-auto max-w-3xl px-4 py-6"
        role="status"
        aria-busy="true"
        aria-label="Cargando armador de sesión…"
      >
        <Skeleton className="mb-2 h-8 w-64" />
        <Skeleton className="mb-6 h-4 w-80" />
        <Skeleton className="mb-4 h-48 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }

  // ── Catalog error state ──
  if (catalog.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-6 text-center"
        >
          <p className="text-sm font-medium text-red-800">
            {resolveErrorMessage(catalog.error)}
          </p>
          <button
            type="button"
            onClick={() => void catalog.refetch()}
            className="mt-3 min-h-10 rounded-lg border border-red-300 px-4 py-2 text-xs font-medium text-red-700 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  // ── Success state ──
  if (result) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <h1 className="mb-1 text-2xl font-semibold text-slate-900">
          Armar sesión técnica
        </h1>

        {/* Age-mix notice */}
        <div className="mt-4 mb-4">
          <MixedAgeNotice mixes_age_bands={result.mixes_age_bands} />
        </div>

        {/* Confirmation banner */}
        <div
          role="alert"
          className="rounded-xl border border-emerald-300 bg-emerald-50 p-5"
        >
          <p className="text-sm font-semibold text-emerald-900">
            Sesión guardada correctamente
          </p>
          <p className="mt-1 text-sm text-emerald-800">
            Se crearon {result.items.length}{" "}
            {result.items.length === 1 ? "ejercicio" : "ejercicios"} en la sesión.
            Puedes verla y registrar asistencia desde la lista de sesiones.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              to={`/training/sessions/${result.training_session_id}`}
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
            >
              Ver sesión
            </Link>
            <Link
              to="/training/sessions"
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-emerald-300 bg-white px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50"
            >
              Lista de sesiones
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Main form state ──
  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-semibold text-slate-900">
        Armar sesión técnica
      </h1>
      <p className="mb-6 text-sm text-slate-500">
        Selecciona ejercicios para cada segmento, define los datos de la sesión
        y guárdala. Aparecerá en el calendario y en la lista de sesiones.
      </p>

      <SessionAssembler
        exercises={catalog.data?.items ?? []}
        athletes={athletes.data?.items ?? []}
        onSubmit={handleSubmit}
        isPending={assemble.isPending}
        errorMessage={mutationError}
      />
    </div>
  );
}

export default SessionBuilderPage;
