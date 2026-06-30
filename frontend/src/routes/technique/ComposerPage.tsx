/**
 * ComposerPage — /technique/composer
 *
 * Phase B (US3): drag-and-drop gymkhana circuit composer that assembles
 * multiple catalog exercises into one combined training session.
 *
 * Bundle isolation (T030): KonvaCanvas is loaded via React.lazy() / dynamic
 * import so react-konva + konva never enter the shared bundle. This page
 * itself is already lazy-loaded from App.tsx (T025 budget preserved).
 *
 * Route params (via searchParams):
 *   ?combinedExerciseId=N  — re-edit path: loads the synthetic exercise's
 *                            layout_json back into the canvas (T034, SC-006).
 *
 * State flow:
 *   1. elements (ComposedElement[]) — canvas state; managed here, passed to
 *      both KonvaCanvas (drag editor) and AccessibleControls (keyboard fallback).
 *   2. selectedId — which element is selected/highlighted in both views.
 *   3. On save → builds GymkhanaLayout → POST assemble with combined_layout.
 *   4. On success → stores combined_exercise_id for re-edit URL state.
 *
 * Privacy (FR-019): labels validated by piiGuard before entering elements[].
 * RBAC: coach/admin (gated in App.tsx via ProtectedRoute).
 */

import { lazy, Suspense, useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { AccessibleControls } from "@/components/technique/composer/AccessibleControls";
import { CircuitDiagram } from "@/components/technique/CircuitDiagram";
import { MixedAgeNotice } from "@/components/technique/MixedAgeNotice";
import { SessionAssembler } from "@/components/technique/SessionAssembler";
import { Skeleton } from "@/components/ui/skeleton";
import { mapTechniqueError } from "@/api/technique";
import {
  useAssembleTechniqueSession,
  useTechniqueCatalog,
  useTechniqueExercise,
} from "@/hooks/technique/useTechnique";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import type {
  AssembleSessionInput,
  AssembleSessionResult,
  CircuitElementKind,
  GymkhanaLayout,
} from "@/types/technique.types";
import type { ComposedElement } from "@/components/technique/composer/KonvaCanvas";

// ---------------------------------------------------------------------------
// T030: KonvaCanvas as a lazy dynamic chunk — react-konva stays out of the
// shared bundle. Only imported when /technique/composer is rendered.
// ---------------------------------------------------------------------------

const KonvaCanvas = lazy(() =>
  import("@/components/technique/composer/KonvaCanvas").then((m) => ({
    default: m.KonvaCanvas,
  })),
);

// ---------------------------------------------------------------------------
// Canvas logical dimensions (shared with piiGuard/BackendLayout)
// ---------------------------------------------------------------------------

const CANVAS_W = 100;
const CANVAS_H = 60;

// ---------------------------------------------------------------------------
// Helpers — convert between ComposedElement[] and GymkhanaLayout
// ---------------------------------------------------------------------------

function toGymkhanaLayout(elements: ComposedElement[]): GymkhanaLayout {
  return {
    width: CANVAS_W,
    height: CANVAS_H,
    elements: elements.map(({ _id: _, ...el }) => el),
  };
}

function fromGymkhanaLayout(layout: GymkhanaLayout): ComposedElement[] {
  return layout.elements.map((el) => ({
    ...el,
    _id: crypto.randomUUID(),
  }));
}

// Default position for newly added elements — spread diagonally so they don't stack.
function defaultPosition(count: number): { x: number; y: number } {
  const offset = (count % 10) * 5;
  return {
    x: Math.min(20 + offset, CANVAS_W - 10),
    y: Math.min(15 + offset, CANVAS_H - 10),
  };
}

// ---------------------------------------------------------------------------
// Cold-start / error helper (matches SessionBuilderPage pattern)
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

export function ComposerPage() {
  const uid = useId();

  // ── Re-edit path: read combinedExerciseId from URL ──
  const [searchParams] = useSearchParams();
  const combinedExerciseIdParam = searchParams.get("combinedExerciseId");
  const initCombinedExerciseId = combinedExerciseIdParam
    ? Number(combinedExerciseIdParam)
    : null;

  // ── Canvas state ──
  const [elements, setElements] = useState<ComposedElement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Track the synthetic exercise id for re-edit (set from URL or after first save)
  const [combinedExerciseId, setCombinedExerciseId] = useState<number | null>(
    initCombinedExerciseId,
  );

  // ── Session result (after save) ──
  const [result, setResult] = useState<AssembleSessionResult | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  // ── Server data ──
  const catalog = useTechniqueCatalog();
  const athletes = useAthletes();
  const assemble = useAssembleTechniqueSession();

  // T034: load the synthetic exercise's layout_json for re-edit
  const {
    data: syntheticExercise,
    isLoading: loadingLayout,
  } = useTechniqueExercise(combinedExerciseId ?? 0, combinedExerciseId !== null);

  // Initialize canvas from layout_json on re-open
  useEffect(() => {
    if (syntheticExercise?.layout_json && elements.length === 0) {
      setElements(fromGymkhanaLayout(syntheticExercise.layout_json));
    }
    // Only run when the synthetic exercise first loads (avoid overwriting on re-render)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syntheticExercise]);

  // ── Element management callbacks ──

  function handleAddElement(kind: CircuitElementKind) {
    const pos = defaultPosition(elements.length);
    const el: ComposedElement = {
      _id: crypto.randomUUID(),
      kind,
      x: pos.x,
      y: pos.y,
      rotation: 0,
      style: kind === "line" ? "dashed" : undefined,
    };
    setElements((prev) => [...prev, el]);
    setSelectedId(el._id);
  }

  function handleChange(
    id: string,
    updates: Partial<Omit<ComposedElement, "_id" | "kind">>,
  ) {
    setElements((prev) =>
      prev.map((el) => (el._id === id ? { ...el, ...updates } : el)),
    );
  }

  function handleRemove(id: string) {
    setElements((prev) => prev.filter((el) => el._id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  // ── Current layout (derived) for static preview ──
  const currentLayout: GymkhanaLayout = toGymkhanaLayout(elements);
  const hasElements = elements.length > 0;

  // ── Save flow ──
  function handleAssemble(input: AssembleSessionInput) {
    setMutationError(null);
    setResult(null);

    const payload: AssembleSessionInput = {
      ...input,
      combined_layout: hasElements ? currentLayout : null,
      combined_exercise_id: combinedExerciseId ?? null,
    };

    assemble.mutate(payload, {
      onSuccess: (data) => {
        if (data.combined_exercise_id) {
          setCombinedExerciseId(data.combined_exercise_id);
        }
        setResult(data);
      },
      onError: (err) => {
        setMutationError(mapTechniqueError(err).message);
      },
    });
  }

  // ── Loading ──
  const isLoading = catalog.isLoading || athletes.isLoading || loadingLayout;

  if (isLoading) {
    return (
      <div
        className="mx-auto max-w-4xl px-4 py-6"
        role="status"
        aria-busy="true"
        aria-label="Cargando compositor de gymkhana…"
      >
        <Skeleton className="mb-2 h-8 w-72" />
        <Skeleton className="mb-6 h-4 w-80" />
        <Skeleton className="mb-4 h-64 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }

  // ── Catalog error ──
  if (catalog.isError) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-6">
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
    const reEditParams = result.combined_exercise_id
      ? `?combinedExerciseId=${result.combined_exercise_id}`
      : "";

    return (
      <div className="mx-auto max-w-4xl px-4 py-6">
        <h1 className="mb-1 text-2xl font-semibold text-slate-900">
          Compositor de gymkhana
        </h1>

        <div className="mt-4 mb-4">
          <MixedAgeNotice mixes_age_bands={result.mixes_age_bands} />
        </div>

        {/* Static preview of the saved circuit */}
        {result.combined_exercise_id && currentLayout.elements.length > 0 && (
          <div className="mb-6">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Circuito combinado guardado
            </p>
            <CircuitDiagram
              layout={currentLayout}
              altText="Circuito de gymkhana combinado creado en el compositor"
            />
          </div>
        )}

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

            {/* Re-edit link (FR-015) */}
            {result.combined_exercise_id && (
              <Link
                to={`/technique/composer${reEditParams}`}
                onClick={() => {
                  setResult(null);
                  setMutationError(null);
                }}
                className="inline-flex min-h-11 items-center justify-center rounded-lg border border-emerald-300 bg-white px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50"
              >
                Editar circuito
              </Link>
            )}

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

  // ── Main composer view ──
  const isReEdit = combinedExerciseId !== null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-900">
          {isReEdit ? "Editar circuito de gymkhana" : "Compositor de gymkhana"}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {isReEdit
            ? "Modifica el circuito combinado y guarda para actualizar la sesión existente."
            : "Diseña el circuito combinado y selecciona los ejercicios del catálogo para crear una sesión de gymkhana grupal."}
        </p>
        {isReEdit && (
          <p className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5 inline-block">
            Editando circuito existente — al guardar, actualizará la misma sesión.
          </p>
        )}
      </div>

      {/* ── Circuit canvas section ── */}
      <div className="mb-6">
        <h2
          id={`${uid}-canvas-heading`}
          className="mb-3 text-base font-semibold text-slate-900"
        >
          Circuito combinado
        </h2>

        {/* Konva editor — loaded lazily (T030) */}
        <Suspense
          fallback={
            <div
              className="flex h-64 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-sm text-slate-500"
              role="status"
            >
              Cargando editor de circuito…
            </div>
          }
        >
          <KonvaCanvas
            canvasWidth={CANVAS_W}
            canvasHeight={CANVAS_H}
            elements={elements}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onChange={handleChange}
          />
        </Suspense>

        {/* Canvas usage hint */}
        <p className="mt-2 text-xs text-slate-400">
          Arrastra los elementos para posicionarlos. Haz clic para seleccionar y
          usar el control de rotación. Usa los controles accesibles a continuación
          si prefieres teclado.
        </p>
      </div>

      {/* ── Accessible controls (T031 / FR-018) ── */}
      <div className="mb-6">
        <AccessibleControls
          elements={elements}
          selectedId={selectedId}
          canvasWidth={CANVAS_W}
          canvasHeight={CANVAS_H}
          onSelect={setSelectedId}
          onAdd={handleAddElement}
          onChange={handleChange}
          onRemove={handleRemove}
        />
      </div>

      {/* ── Static preview (T034: read-only CircuitDiagram) ── */}
      {hasElements && (
        <div className="mb-6">
          <h2 className="mb-2 text-base font-semibold text-slate-900">
            Vista previa del circuito
          </h2>
          <p className="mb-3 text-xs text-slate-500">
            Render estático del circuito — idéntico al que aparecerá en los documentos.
          </p>
          <CircuitDiagram
            layout={currentLayout}
            altText="Vista previa del circuito combinado de gymkhana"
          />
        </div>
      )}

      {/* ── Save flow: session assembler ── */}
      <div className="border-t border-slate-200 pt-6">
        <h2 className="mb-4 text-base font-semibold text-slate-900">
          Datos de la sesión y ejercicios
        </h2>
        {!hasElements && (
          <div
            role="status"
            className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
          >
            Agrega al menos un elemento al circuito antes de guardar la sesión.
          </div>
        )}

        <SessionAssembler
          exercises={catalog.data?.items ?? []}
          athletes={athletes.data?.items ?? []}
          onSubmit={handleAssemble}
          isPending={assemble.isPending}
          errorMessage={mutationError}
        />
      </div>
    </div>
  );
}

export default ComposerPage;
