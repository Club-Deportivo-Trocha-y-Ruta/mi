/**
 * BlockBuilderPage — página de armado de bloques de fuerza y adjunto a una
 * sesión de entrenamiento existente (feature 021 / T026, US2).
 *
 * Rutas:
 *   - /strength/blocks/new  → modo creación
 *   - /strength/blocks/:id  → modo edición (carga el bloque existente)
 *
 * Flujo:
 *   1. Carga el catálogo de ejercicios (BlockAssembler) y, en modo edición,
 *      el bloque existente.
 *   2. El entrenador arma/edita el bloque (metadatos + entradas ordenables)
 *      y lo guarda vía useSaveBlock (POST/PUT /api/strength/blocks).
 *   3. Tras guardar con éxito, se habilita el selector "Adjuntar a una
 *      sesión de entrenamiento": busca/filtra entre las sesiones existentes
 *      del club (useTrainingSessions) y adjunta el bloque con
 *      useAttachBlock (POST /blocks/{id}/attach). No se duplica la UI de
 *      creación de sesiones — se enlaza al asistente existente
 *      (`/training/sessions/new`) para el caso de "necesito una sesión
 *      nueva".
 *
 * Estados cubiertos: loading (skeleton), error de carga del bloque (404 sin
 * reintentar), error de guardado (inline), guardado exitoso + adjunto
 * pendiente/éxito/error. Coach/admin only — gating en App.tsx.
 *
 * Mirror de `routes/technique/SessionBuilderPage.tsx` (feature 018) para el
 * patrón de estados; el bloque "adjuntar a sesión" es específico de 021
 * porque los bloques de fuerza son un objeto reutilizable independiente de
 * la sesión (a diferencia de una sesión técnica, que se crea de una vez).
 */
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, RefreshCw } from "lucide-react";

import {
  BlockAssembler,
  type BlockAssemblerEntry,
  type BlockAssemblerSubmitInput,
} from "@/components/strength/BlockAssembler";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { extractAgeBandGuardrail, mapStrengthError } from "@/api/strength";
import {
  useAttachBlock,
  useSaveBlock,
  useStrengthBlock,
  useStrengthCatalog,
} from "@/hooks/strength/useStrength";
import { useTrainingSessions } from "@/api/trainingSessions";
import type { TrainingSession } from "@/types/trainingSession.types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Etiqueta legible para una sesión en el selector de adjunto. */
function sessionLabel(session: TrainingSession): string {
  const date = session.scheduled_date || "Sin fecha";
  const place = session.location?.trim() || "Sin lugar";
  const focus = session.technical_focus?.trim();
  return focus ? `${date} — ${place} — ${focus}` : `${date} — ${place}`;
}

function matchesQuery(session: TrainingSession, query: string): boolean {
  if (!query.trim()) return true;
  const q = query.trim().toLowerCase();
  return (
    session.location?.toLowerCase().includes(q) ||
    session.technical_focus?.toLowerCase().includes(q) ||
    session.scheduled_date?.toLowerCase().includes(q) ||
    false
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function BlockBuilderPage() {
  const { id: rawId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const blockId = rawId ? Number(rawId) || 0 : 0;
  const isEditMode = blockId > 0;

  const catalog = useStrengthCatalog();
  const blockQuery = useStrengthBlock(blockId, isEditMode);
  const saveBlock = useSaveBlock();
  const attachBlock = useAttachBlock();

  const [saveErrorMessage, setSaveErrorMessage] = useState<string | null>(
    null,
  );
  const [savedBlockId, setSavedBlockId] = useState<number | null>(
    isEditMode ? blockId : null,
  );
  const [attachQuery, setAttachQuery] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(
    null,
  );
  const [attachErrorMessage, setAttachErrorMessage] = useState<string | null>(
    null,
  );
  const [attachedSession, setAttachedSession] =
    useState<TrainingSession | null>(null);

  const sessions = useTrainingSessions();

  const filteredSessions = useMemo(() => {
    const items = sessions.data ?? [];
    return items.filter((s) => matchesQuery(s, attachQuery));
  }, [sessions.data, attachQuery]);

  // ── Guardado del bloque ────────────────────────────────────────────────

  // T031: async + rethrow — BlockAssembler necesita capturar el rechazo para
  // detectar el 422 AGE_BAND_GUARDRAIL (FR-011, US3) y abrir su propio
  // diálogo de anulación en vez de un error genérico; para cualquier otro
  // error, esta página sigue mostrando `saveErrorMessage` como antes.
  async function handleSubmit(input: BlockAssemblerSubmitInput) {
    setSaveErrorMessage(null);
    try {
      const data = await saveBlock.mutateAsync({
        id: isEditMode ? blockId : undefined,
        input,
      });
      setSavedBlockId(data.id);
    } catch (err) {
      if (!extractAgeBandGuardrail(err)) {
        setSaveErrorMessage(mapStrengthError(err).message);
      }
      throw err;
    }
  }

  // ── Adjunto a sesión existente ──────────────────────────────────────────

  function handleAttach() {
    if (!savedBlockId || !selectedSessionId) return;
    setAttachErrorMessage(null);
    attachBlock.mutate(
      { blockId: savedBlockId, trainingSessionId: selectedSessionId },
      {
        onSuccess: () => {
          const session = (sessions.data ?? []).find(
            (s) => s.id === selectedSessionId,
          );
          setAttachedSession(session ?? null);
        },
        onError: (err) => {
          setAttachErrorMessage(mapStrengthError(err).message);
        },
      },
    );
  }

  // ── Estado: cargando catálogo o bloque existente ────────────────────────

  const isLoading = catalog.isLoading || (isEditMode && blockQuery.isLoading);

  if (isLoading) {
    return (
      <div
        className="mx-auto max-w-3xl px-4 py-6"
        role="status"
        aria-busy="true"
        aria-label="Cargando armador de bloque…"
      >
        <Skeleton className="mb-2 h-8 w-64" />
        <Skeleton className="mb-6 h-4 w-80" />
        <Skeleton className="mb-4 h-48 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }

  // ── Estado: error al cargar el bloque (edición) ─────────────────────────

  if (isEditMode && (blockQuery.isError || !blockQuery.data)) {
    const info = mapStrengthError(blockQuery.error);
    const is404 = info.kind === "not_found";
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-5"
        >
          <div className="flex items-center gap-2 text-red-700">
            <AlertTriangle size={18} aria-hidden="true" />
            <span className="text-sm font-semibold">
              No se pudo cargar el bloque
            </span>
          </div>
          <p className="text-sm text-red-600">
            {is404
              ? "No se encontró este bloque o fue eliminado."
              : info.message}
          </p>
          {!is404 && (
            <Button
              variant="outline"
              onClick={() => void blockQuery.refetch()}
              className="min-h-12 gap-1.5"
            >
              <RefreshCw size={14} aria-hidden="true" />
              Reintentar
            </Button>
          )}
        </div>
      </div>
    );
  }

  // ── Estado: error al cargar el catálogo ─────────────────────────────────

  if (catalog.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-6 text-center"
        >
          <p className="text-sm font-medium text-red-800">
            No se pudo cargar el catálogo de ejercicios. Intenta de nuevo.
          </p>
          <Button
            variant="outline"
            onClick={() => void catalog.refetch()}
            className="mt-3 min-h-10"
          >
            Reintentar
          </Button>
        </div>
      </div>
    );
  }

  // ── Valores por defecto en modo edición ─────────────────────────────────

  const defaultValues = isEditMode && blockQuery.data
    ? {
        name: blockQuery.data.name,
        target_age_band: blockQuery.data.target_age_band,
        duration_target_min: blockQuery.data.duration_target_min,
      }
    : undefined;

  const defaultEntries: BlockAssemblerEntry[] | undefined =
    isEditMode && blockQuery.data
      ? blockQuery.data.entries
          .slice()
          .sort((a, b) => a.position - b.position)
          .map((entry) => ({
            exercise_id: entry.exercise.id,
            name: entry.exercise.name,
            duration_min: entry.duration_min,
            reps: entry.reps ?? "",
            is_age_override: entry.is_age_override,
            override_note: entry.override_note,
          }))
      : undefined;

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-semibold text-slate-900">
        {isEditMode ? "Editar bloque de fuerza" : "Armar bloque de fuerza"}
      </h1>
      <p className="mb-6 text-sm text-slate-500">
        Selecciona ejercicios, ajusta duración y repeticiones, y guarda el
        bloque. Luego puedes adjuntarlo a una sesión de entrenamiento
        existente.
      </p>

      <BlockAssembler
        exercises={catalog.data?.items ?? []}
        onSubmit={handleSubmit}
        isPending={saveBlock.isPending}
        errorMessage={saveErrorMessage}
        defaultValues={defaultValues}
        defaultEntries={defaultEntries}
      />

      {/* ── Adjuntar a sesión de entrenamiento existente ── */}
      {savedBlockId && (
        <Card className="mt-8">
          <CardContent className="py-5">
            <h2 className="mb-1 text-base font-semibold text-slate-900">
              Adjuntar a una sesión de entrenamiento
            </h2>
            <p className="mb-4 text-sm text-slate-500">
              Bloque guardado correctamente. Búscalo entre las sesiones
              existentes del club y adjúntalo, o{" "}
              <Link
                to="/training/sessions/new"
                className="font-medium text-primary underline underline-offset-2"
              >
                crea una sesión nueva
              </Link>{" "}
              desde el módulo de Sesiones de Entrenamiento y vuelve aquí para
              adjuntar el bloque.
            </p>

            {attachedSession ? (
              <div
                role="alert"
                className="rounded-xl border border-emerald-300 bg-emerald-50 p-4"
              >
                <p className="text-sm font-semibold text-emerald-900">
                  Bloque adjuntado correctamente
                </p>
                <p className="mt-1 text-sm text-emerald-800">
                  Se adjuntó a la sesión: {sessionLabel(attachedSession)}
                </p>
                <div className="mt-3 flex flex-wrap gap-3">
                  <Link
                    to={`/training/sessions/${attachedSession.id}`}
                    className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
                  >
                    Ver sesión
                  </Link>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => navigate(`/strength/blocks/${savedBlockId}`)}
                  >
                    Seguir editando el bloque
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <label htmlFor="attach-session-search" className="sr-only">
                  Buscar sesión de entrenamiento
                </label>
                <input
                  id="attach-session-search"
                  type="search"
                  value={attachQuery}
                  onChange={(e) => setAttachQuery(e.target.value)}
                  placeholder="Buscar por fecha, lugar o enfoque técnico…"
                  className="mb-3 min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
                />

                {sessions.isLoading ? (
                  <Skeleton className="h-24 w-full rounded-lg" />
                ) : sessions.isError ? (
                  <p role="alert" className="text-sm text-red-600">
                    No se pudieron cargar las sesiones de entrenamiento.
                  </p>
                ) : filteredSessions.length === 0 ? (
                  <p className="text-sm text-slate-400 italic">
                    No hay sesiones que coincidan con la búsqueda.
                  </p>
                ) : (
                  <div
                    role="radiogroup"
                    aria-label="Sesiones de entrenamiento disponibles"
                    className="mb-4 max-h-64 space-y-1 overflow-y-auto"
                  >
                    {filteredSessions.map((session) => (
                      <label
                        key={session.id}
                        className="flex min-h-12 cursor-pointer items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 hover:bg-slate-50 has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                      >
                        <input
                          type="radio"
                          name="attach-session"
                          value={session.id}
                          checked={selectedSessionId === session.id}
                          onChange={() => setSelectedSessionId(session.id)}
                          className="h-4 w-4"
                        />
                        {sessionLabel(session)}
                      </label>
                    ))}
                  </div>
                )}

                {attachErrorMessage && (
                  <p role="alert" className="mb-3 text-sm text-red-600">
                    {attachErrorMessage}
                  </p>
                )}

                <Button
                  type="button"
                  disabled={!selectedSessionId || attachBlock.isPending}
                  onClick={handleAttach}
                >
                  {attachBlock.isPending
                    ? "Adjuntando…"
                    : "Adjuntar a la sesión seleccionada"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default BlockBuilderPage;
