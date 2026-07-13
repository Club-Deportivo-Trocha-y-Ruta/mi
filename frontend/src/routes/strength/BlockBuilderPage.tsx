/**
 * BlockBuilderPage — página de armado de bloques de fuerza y adjunto a una
 * sesión de entrenamiento existente (feature 021 / T026, US2; preselect +
 * auto-adjunto unificados en feature 032 / T018-T019, US1).
 *
 * Rutas:
 *   - /strength/blocks/new                  → modo creación, sin sesión conocida
 *   - /strength/blocks/new?session_id={id}  → modo creación, sesión ya elegida
 *   - /strength/blocks/:id                  → modo edición (carga el bloque existente)
 *
 * Flujo (modo creación, feature 032 — contracts/unified-attach-flow.md):
 *   0. Si no llega `?session_id=` en la URL, primero se pregunta "¿a qué
 *      sesión?" vía `SessionPickerDialog` — el formulario de armado ni
 *      siquiera se muestra hasta tener una sesión resuelta (entry points
 *      2/3 del contrato). Al elegir, se navega con
 *      `?session_id={id}` (replace) y converge al paso 1.
 *   1. Con `?session_id=` presente (entry point 1, o ya resuelto en el paso
 *      0), la sesión se muestra como un resumen bloqueado de solo lectura
 *      (texto estático + ícono Lock/Pencil — convención "locked read-only
 *      summary" de la feature 015) y el selector buscable de sesiones
 *      (`role="radiogroup"`) NO se renderiza.
 *   2. El entrenador arma el bloque (metadatos + entradas ordenables) y lo
 *      guarda vía useSaveBlock (POST/PUT /api/strength/blocks).
 *   3. Con sesión bloqueada, el guardado exitoso dispara automáticamente
 *      useAttachBlock y navega a `/training/sessions/{id}?section=plan` —
 *      no hay una segunda elección manual de sesión para el caso común.
 *
 * Modo edición (`/strength/blocks/:id`, sin `?session_id=`): conserva el
 * flujo previo — el selector buscable de sesiones existentes sigue
 * disponible tras guardar, sin la compuerta de "¿a qué sesión?" (no es uno
 * de los entry points del contrato 032; el coach puede seguir editando un
 * bloque sin verse forzado a elegir sesión).
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
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { AlertTriangle, Loader2, Lock, Pencil, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  BlockAssembler,
  type BlockAssemblerEntry,
  type BlockAssemblerSubmitInput,
} from "@/components/strength/BlockAssembler";
import { SessionPickerDialog } from "@/components/training/session-plan/SessionPickerDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  extractAgeBandGuardrail,
  isAlreadyAttachedError,
  mapStrengthError,
} from "@/api/strength";
import {
  useAttachBlock,
  useSaveBlock,
  useStrengthBlock,
  useStrengthCatalog,
} from "@/hooks/strength/useStrength";
import { useTrainingSession, useTrainingSessions } from "@/api/trainingSessions";
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
// Resumen bloqueado de solo lectura (feature 032, T018)
//
// Convención "locked read-only summary" de la feature 015 (CLAUDE.md,
// `specs/015-prefill-import-from-competition`): texto estático + ícono
// Lock/Pencil — nunca un input `disabled` — para preservar navegabilidad por
// teclado y lectura de screen-reader.
// ---------------------------------------------------------------------------

interface LockedSessionSummaryProps {
  session: TrainingSession | undefined;
  isLoading: boolean;
  isError: boolean;
  /** Oculta el enlace "Cambiar sesión" una vez que ya se guardó el bloque. */
  canChange: boolean;
}

function LockedSessionSummary({
  session,
  isLoading,
  isError,
  canChange,
}: LockedSessionSummaryProps) {
  return (
    <div
      className="mb-6 rounded-lg border border-[rgba(34,42,53,0.08)] bg-light-gray/30 p-4"
      aria-label="Sesión de entrenamiento (bloqueada)"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Lock size={14} aria-hidden="true" className="text-mid-gray" />
          <h2 className="text-sm font-semibold text-slate-900">
            Sesión de entrenamiento
          </h2>
          <span className="rounded-full bg-light-gray px-2 py-0.5 text-[11px] font-medium text-mid-gray">
            Bloqueado
          </span>
        </div>
        {canChange && (
          <Link
            to="/strength/blocks/new"
            replace
            className="inline-flex min-h-11 items-center gap-1 rounded-lg px-2 text-xs font-medium text-primary hover:text-primary/80"
          >
            <Pencil size={12} aria-hidden="true" />
            Cambiar sesión
          </Link>
        )}
      </div>
      {isLoading ? (
        <Skeleton className="h-4 w-2/3" />
      ) : isError || !session ? (
        <p className="text-sm text-red-600">
          No se pudo cargar la sesión seleccionada.
        </p>
      ) : (
        <p className="text-sm font-medium text-slate-800">
          {sessionLabel(session)}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function BlockBuilderPage() {
  const { id: rawId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const blockId = rawId ? Number(rawId) || 0 : 0;
  const isEditMode = blockId > 0;

  // Feature 032 (T018) — sesión preseleccionada vía `?session_id=`
  // (research.md R5). Solo modo creación: editar un bloque existente no es
  // uno de los entry points del contrato de adjunto unificado
  // (contracts/unified-attach-flow.md), así que conserva su flujo previo.
  const sessionIdParam = Number(searchParams.get("session_id")) || 0;
  const lockedSessionId = sessionIdParam > 0 ? sessionIdParam : null;
  const needsSessionPick = !isEditMode && lockedSessionId == null;

  const [pickerOpen, setPickerOpen] = useState(needsSessionPick);

  const catalog = useStrengthCatalog();
  const blockQuery = useStrengthBlock(blockId, isEditMode);
  const lockedSessionQuery = useTrainingSession(
    lockedSessionId ?? 0,
    lockedSessionId != null,
  );
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

  const sessions = useTrainingSessions(undefined, !lockedSessionId);

  const filteredSessions = useMemo(() => {
    const items = sessions.data ?? [];
    return items.filter((s) => matchesQuery(s, attachQuery));
  }, [sessions.data, attachQuery]);

  // ── Guardado del bloque ────────────────────────────────────────────────

  // T031: async + rethrow — BlockAssembler necesita capturar el rechazo para
  // detectar el 422 AGE_BAND_GUARDRAIL (FR-011, US3) y abrir su propio
  // diálogo de anulación en vez de un error genérico; para cualquier otro
  // error, esta página sigue mostrando `saveErrorMessage` como antes.
  //
  // T019: con sesión bloqueada (`lockedSessionId`), el guardado exitoso
  // dispara el adjunto automáticamente — no hay una segunda elección manual.
  async function handleSubmit(input: BlockAssemblerSubmitInput) {
    setSaveErrorMessage(null);
    try {
      const data = await saveBlock.mutateAsync({
        id: isEditMode ? blockId : undefined,
        input,
      });
      setSavedBlockId(data.id);
      if (lockedSessionId != null) {
        runAutoAttach(data.id, lockedSessionId);
      }
    } catch (err) {
      if (!extractAgeBandGuardrail(err)) {
        setSaveErrorMessage(mapStrengthError(err).message);
      }
      throw err;
    }
  }

  // ── Adjunto automático a la sesión bloqueada (T019) ─────────────────────

  function runAutoAttach(blockIdToAttach: number, trainingSessionId: number) {
    setAttachErrorMessage(null);
    attachBlock.mutate(
      { blockId: blockIdToAttach, trainingSessionId },
      {
        onSuccess: () => {
          toast.success("Bloque de fuerza adjuntado a la sesión.");
          navigate(`/training/sessions/${trainingSessionId}?section=plan`);
        },
        onError: (err) => {
          // 409 "ya está adjunto" (research.md R2/R11) — el resultado que el
          // coach buscaba ya existe; sigue igual que un adjunto exitoso.
          if (isAlreadyAttachedError(err)) {
            toast.success("Bloque de fuerza adjuntado a la sesión.");
            navigate(`/training/sessions/${trainingSessionId}?section=plan`);
            return;
          }
          const message = mapStrengthError(err).message;
          setAttachErrorMessage(message);
          toast.error(message);
        },
      },
    );
  }

  // ── Adjunto a sesión existente (modo edición, sin sesión bloqueada) ─────

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

  // ── Estado: sin sesión conocida — se pregunta primero (T018) ───────────

  if (needsSessionPick) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <SessionPickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          onSelect={(sessionId) =>
            navigate(`/strength/blocks/new?session_id=${sessionId}`, {
              replace: true,
            })
          }
          title="¿A qué sesión vas a adjuntar el bloque?"
          description="Elegí la sesión de entrenamiento antes de armar el bloque de fuerza."
        />
        {!pickerOpen && (
          <div className="rounded-xl border border-slate-200 bg-white p-8 text-center">
            <p className="mb-4 text-sm text-slate-600">
              Elegí una sesión de entrenamiento para armar el bloque de
              fuerza.
            </p>
            <Button type="button" onClick={() => setPickerOpen(true)}>
              Elegir sesión
            </Button>
          </div>
        )}
      </div>
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
        {lockedSessionId != null
          ? "Selecciona ejercicios, ajusta duración y repeticiones, y guarda el bloque. Se adjuntará automáticamente a la sesión elegida."
          : "Selecciona ejercicios, ajusta duración y repeticiones, y guarda el bloque. Luego puedes adjuntarlo a una sesión de entrenamiento existente."}
      </p>

      {lockedSessionId != null && (
        <LockedSessionSummary
          session={lockedSessionQuery.data}
          isLoading={lockedSessionQuery.isLoading}
          isError={lockedSessionQuery.isError}
          canChange={!savedBlockId}
        />
      )}

      <BlockAssembler
        exercises={catalog.data?.items ?? []}
        onSubmit={handleSubmit}
        isPending={saveBlock.isPending}
        errorMessage={saveErrorMessage}
        defaultValues={defaultValues}
        defaultEntries={defaultEntries}
      />

      {/* ── T019: adjunto automático a la sesión bloqueada ── */}
      {savedBlockId && lockedSessionId != null && (
        <Card className="mt-8">
          <CardContent className="py-5">
            {attachBlock.isPending ? (
              <p
                role="status"
                aria-busy="true"
                className="flex items-center gap-2 text-sm text-slate-600"
              >
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Adjuntando a la sesión…
              </p>
            ) : attachErrorMessage ? (
              <div
                role="alert"
                className="rounded-xl border border-red-200 bg-red-50 p-4"
              >
                <p className="text-sm text-red-700">{attachErrorMessage}</p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-3"
                  disabled={attachBlock.isPending}
                  onClick={() => runAutoAttach(savedBlockId, lockedSessionId)}
                >
                  {attachBlock.isPending ? "Reintentando…" : "Reintentar adjunto"}
                </Button>
              </div>
            ) : (
              <p className="text-sm text-slate-500">
                Bloque guardado. Adjuntando a la sesión…
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Adjuntar a sesión de entrenamiento existente (modo edición, sin sesión bloqueada) ── */}
      {savedBlockId && lockedSessionId == null && (
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
