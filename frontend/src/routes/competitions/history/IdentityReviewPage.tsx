/**
 * IdentityReviewPage — revisión de identidad de competidores históricos
 * (feature 044, US4).
 *
 * Ruta: /competitions/identity-review
 * Acceso: coach + admin (gate el commit de una carga histórica, FR-016…22).
 *
 * Flujo por defecto ("Pendientes"): un candidato a la vez, dos tarjetas lado
 * a lado con las señales en palabras y dos botones ≥48 px. Al decidir, la
 * lista se invalida y el siguiente candidato pendiente ocupa el lugar — sin
 * navegación extra (objetivo SC-009: una decisión ≤ 15 s).
 *
 * Los demás filtros de estado ("Misma persona" / "Personas distintas" /
 * "Todos") muestran una lista compacta con "Deshacer" por fila, útil para
 * revisar o corregir decisiones ya tomadas. La paginación de esa lista usa
 * `page_size` (fijo en 20, `identity_review.py::DEFAULT_PAGE_SIZE`) tal como
 * lo devuelve `GET /candidates` — nunca un valor asumido en el frontend.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Loader2,
  RefreshCw,
  Undo2,
  UserRoundX,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getIdentityReviewErrorMessage,
  useDecideIdentityCandidate,
  useIdentityCandidates,
  useIdentitySummary,
  useRebuildIdentityCandidates,
  useReverseIdentityCandidate,
} from "@/hooks/race/useIdentityReview";
import type {
  IdentityCandidateRead,
  IdentityCandidateState,
  IdentityDecisionAnswer,
  IdentityRecordRead,
  IdentitySignalCode,
} from "@/types/raceIdentity.types";

// ---------------------------------------------------------------------------
// Copy — señales, tipo de candidato y estado en palabras
// ---------------------------------------------------------------------------

// Mirror de `identity_review.py::SIGNAL_*` (research §Candidate rules). Un
// código no reconocido (señal agregada en el backend después de este
// deploy) cae en la reserva genérica de `signalLabel()` — nunca se muestra
// el código crudo.
const SIGNAL_LABELS: Record<string, string> = {
  same_valida_two_categories:
    "Mismo nombre en dos categorías de la misma válida",
  same_valida_same_category:
    "El mismo nombre aparece dos veces en la misma categoría de una válida",
  sex_conflict: "Sexo registrado distinto entre válidas",
  age_path_backwards:
    "La edad no avanza de forma consistente entre temporadas",
  club_and_city_differ: "Club y ciudad distintos entre válidas",
  multiple_existing_competitors:
    "Este nombre coincide con varios competidores ya registrados",
  age_incompatible_categories:
    "Aparece en categorías de edades que no pueden ser de la misma persona",
  extra_or_missing_surname: "Un apellido de más o de menos entre los nombres",
  inverted_surname_order: "Apellidos en orden invertido",
  spelling_variant: "Los nombres difieren en pocas letras",
};

function signalLabel(signal: IdentitySignalCode): string {
  return SIGNAL_LABELS[signal] ?? "Otra coincidencia detectada por el sistema";
}

const KIND_LABELS: Record<IdentityCandidateRead["kind"], string> = {
  same_person_suspect: "Posible misma persona con nombre distinto",
  homonym_suspect: "Posible homónimo (mismo nombre, personas distintas)",
};

const STATE_LABELS: Record<IdentityCandidateState, string> = {
  pending: "Pendiente",
  same_person: "Misma persona",
  different_people: "Personas distintas",
};

type StateFilterValue = "pending" | "same_person" | "different_people" | "all";

const STATE_FILTER_OPTIONS: { value: StateFilterValue; label: string }[] = [
  { value: "pending", label: "Pendientes" },
  { value: "same_person", label: "Decididos: misma persona" },
  { value: "different_people", label: "Decididos: personas distintas" },
  { value: "all", label: "Todos" },
];

// ---------------------------------------------------------------------------
// Presentación de un registro (nombre impreso, club, ciudad, temporadas...)
// ---------------------------------------------------------------------------

function formatList(values: string[] | number[]): string {
  if (values.length === 0) return "Sin dato";
  return values.join(", ");
}

interface IdentityRecordCardProps {
  record: IdentityRecordRead;
  testId: string;
}

function IdentityRecordCard({ record, testId }: IdentityRecordCardProps) {
  return (
    <Card className="flex-1" data-testid={testId}>
      <CardContent className="space-y-2 p-4">
        <p className="font-display text-lg text-charcoal">
          {record.name_printed}
        </p>
        <dl className="space-y-1 text-sm text-mid-gray">
          <div className="flex gap-1.5">
            <dt className="font-medium text-charcoal">Club:</dt>
            <dd>{record.club || "Sin dato"}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="font-medium text-charcoal">Ciudad:</dt>
            <dd>{record.city || "Sin dato"}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="font-medium text-charcoal">Temporadas:</dt>
            <dd>{formatList(record.seasons)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="font-medium text-charcoal">Categorías:</dt>
            <dd>{formatList(record.category_labels)}</dd>
          </div>
        </dl>
        {record.athlete_linked && (
          <Badge variant="info">Enlazado a un deportista del club</Badge>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Tarjeta de decisión (modo "un candidato a la vez")
// ---------------------------------------------------------------------------

interface DecisionCardProps {
  candidate: IdentityCandidateRead;
  onDecide: (answer: IdentityDecisionAnswer) => void;
  /**
   * `true` mientras la decisión está en vuelo O mientras la cola todavía
   * está trayendo el siguiente candidato tras invalidar la query — no solo
   * `decideMutation.isPending` (ux-review.md MAJOR #2: sin esto, un
   * segundo atajo de teclado rápido puede decidir sobre el candidato
   * equivocado antes de que la pantalla alcance a refrescar).
   */
  isBusy: boolean;
}

function DecisionCard({ candidate, onDecide, isBusy }: DecisionCardProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">
          {KIND_LABELS[candidate.kind] ?? candidate.kind}
        </Badge>
        <Badge variant="outline">Similitud: {candidate.score}%</Badge>
        {candidate.linked_athlete_involved && (
          <Badge variant="warning" data-testid="linked-athlete-chip">
            <Users size={12} className="mr-1" aria-hidden="true" />
            Incluye un deportista enlazado
          </Badge>
        )}
      </div>

      <ul className="space-y-1 rounded-lg bg-light-gray/50 p-3 text-sm text-charcoal">
        {candidate.signals.map((signal) => (
          <li key={signal} className="flex gap-2">
            <span aria-hidden="true">•</span>
            {signalLabel(signal)}
          </li>
        ))}
      </ul>

      <div className="flex flex-col gap-3 sm:flex-row">
        <IdentityRecordCard record={candidate.left} testId="candidate-left" />
        <IdentityRecordCard record={candidate.right} testId="candidate-right" />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          type="button"
          size="lg"
          className="min-h-12 flex-1"
          disabled={isBusy}
          onClick={() => onDecide("same_person")}
          data-testid="decide-same-person"
        >
          {isBusy ? (
            <>
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              Guardando...
            </>
          ) : (
            <>
              Es la misma persona
              {/* Insignia sólida, no texto translúcido: blanco puro sobre
                  el turquesa del botón da apenas ≈2.4:1 (sigue bajo el
                  piso de 4.5:1 AA) — un fondo blanco opaco con texto
                  charcoal garantiza contraste real sin depender del color
                  de fondo del botón (WCAG AA 1.4.3, ux-review.md MAJOR #3) */}
              <span className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-white px-1 text-[10px] font-semibold text-charcoal">
                1
              </span>
            </>
          )}
        </Button>
        <Button
          type="button"
          size="lg"
          variant="outline"
          className="min-h-12 flex-1"
          disabled={isBusy}
          onClick={() => onDecide("different_people")}
          data-testid="decide-different-people"
        >
          {isBusy ? (
            <>
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              Guardando...
            </>
          ) : (
            <>
              Son personas distintas
              <span className="ml-1.5 text-xs opacity-70">(2)</span>
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fila compacta (modo lista — estados decididos)
// ---------------------------------------------------------------------------

interface CandidateRowProps {
  candidate: IdentityCandidateRead;
  onRequestUndo: (candidate: IdentityCandidateRead) => void;
}

function CandidateRow({ candidate, onRequestUndo }: CandidateRowProps) {
  return (
    <Card data-testid={`candidate-row-${candidate.id}`}>
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-medium text-charcoal">
            {candidate.left.name_printed} — {candidate.right.name_printed}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline">
              {STATE_LABELS[candidate.state] ?? candidate.state}
            </Badge>
            <Badge variant="secondary">
              {KIND_LABELS[candidate.kind] ?? candidate.kind}
            </Badge>
            {candidate.linked_athlete_involved && (
              <Badge variant="warning">
                <Users size={12} className="mr-1" aria-hidden="true" />
                Deportista enlazado
              </Badge>
            )}
          </div>
        </div>
        {candidate.state !== "pending" && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0"
            onClick={() => onRequestUndo(candidate)}
            data-testid={`undo-${candidate.id}`}
          >
            <Undo2 size={14} aria-hidden="true" />
            Deshacer
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function IdentityReviewPage() {
  const [stateFilter, setStateFilter] = useState<StateFilterValue>("pending");
  const [page, setPage] = useState(1);
  const [undoTarget, setUndoTarget] = useState<IdentityCandidateRead | null>(
    null,
  );

  useEffect(() => {
    setPage(1);
  }, [stateFilter]);

  const apiState = stateFilter === "all" ? undefined : stateFilter;

  const candidatesQuery = useIdentityCandidates({ state: apiState, page });
  const summaryQuery = useIdentitySummary();

  const decideMutation = useDecideIdentityCandidate();
  const reverseMutation = useReverseIdentityCandidate();
  const rebuildMutation = useRebuildIdentityCandidates();

  const items = candidatesQuery.data?.items ?? [];
  const total = candidatesQuery.data?.total ?? 0;

  const isPendingMode = stateFilter === "pending";
  const activeCandidate = isPendingMode ? items[0] : undefined;

  // ux-review.md MAJOR #2 — `decideMutation.isPending` resuelve apenas
  // llega la respuesta HTTP, antes de que el refetch invalidado (disparado
  // por la propia mutation) reemplace `items[0]` por el siguiente
  // candidato. Mientras `candidatesQuery.isFetching` siga en `true`, la
  // pantalla todavía muestra el par recién decidido — un segundo clic o
  // atajo de teclado en esa ventana debe seguir bloqueado.
  const isBusy = decideMutation.isPending || candidatesQuery.isFetching;

  const decided =
    (summaryQuery.data?.same_person ?? 0) +
    (summaryQuery.data?.different_people ?? 0);
  const totalCandidates = decided + (summaryQuery.data?.pending ?? 0);

  function handleDecide(answer: IdentityDecisionAnswer) {
    if (!activeCandidate || isBusy) return;
    decideMutation.mutate(
      { candidateId: activeCandidate.id, body: { answer } },
      {
        onSuccess: (data) => {
          let message =
            answer === "same_person"
              ? "Registrado: es la misma persona."
              : "Registrado: son personas distintas.";
          if (data.merged) {
            message += ` Se unieron ${data.results_moved} resultado(s) al competidor más antiguo.`;
          }
          toast.success(message);
        },
        onError: (err) => {
          toast.error(getIdentityReviewErrorMessage(err));
          void candidatesQuery.refetch();
        },
      },
    );
  }

  function handleConfirmUndo() {
    if (!undoTarget) return;
    reverseMutation.mutate(
      { candidateId: undoTarget.id },
      {
        onSuccess: (data) => {
          let message = "Decisión deshecha. El candidato vuelve a pendiente.";
          if (data.split) {
            message += ` Se separaron ${data.results_moved} resultado(s)`;
            message +=
              data.links_cleared > 0
                ? ` (${data.links_cleared} perdieron su enlace con el deportista).`
                : ".";
          }
          toast.success(message);
          setUndoTarget(null);
        },
        onError: (err) => {
          toast.error(getIdentityReviewErrorMessage(err));
          setUndoTarget(null);
        },
      },
    );
  }

  function handleRebuild() {
    rebuildMutation.mutate(undefined, {
      onSuccess: (data) => {
        let message = `Candidatos recalculados: ${data.created} nuevos, ${data.pending} pendientes.`;
        if (data.removed > 0) {
          message += ` ${data.removed} sin atletas del club se retiraron de la cola.`;
        }
        if (data.imports_unreadable.length > 0) {
          message += ` ${data.imports_unreadable.length} archivo(s) no se pudieron leer y quedaron fuera del recálculo.`;
        }
        toast.success(message);
      },
      onError: (err) => {
        toast.error(getIdentityReviewErrorMessage(err));
      },
    });
  }

  // ---------------------------------------------------------------------
  // Atajos de teclado — sólo en el modo "un candidato a la vez" y con un
  // diálogo cerrado (el diálogo de deshacer maneja su propio foco).
  // ---------------------------------------------------------------------
  useEffect(() => {
    if (!isPendingMode || !activeCandidate || undoTarget) return;

    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
      ) {
        return;
      }
      if (event.key === "1") {
        event.preventDefault();
        handleDecide("same_person");
      } else if (event.key === "2") {
        event.preventDefault();
        handleDecide("different_people");
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // `isBusy` (no solo `decideMutation.isPending`) en las deps: el listener
    // debe re-crearse — y por lo tanto volver a capturar un `handleDecide`
    // fresco — apenas cambia `candidatesQuery.isFetching`, o un segundo "1"
    // disparado durante el refetch quedaría atado a un closure viejo que
    // todavía cree que la pantalla no está ocupada (ux-review.md MAJOR #2).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPendingMode, activeCandidate?.id, undoTarget, isBusy]);

  const pageSize = candidatesQuery.data?.page_size ?? items.length;
  const hasNextPage = pageSize > 0 && page * pageSize < total;
  const hasPrevPage = page > 1;

  return (
    <section className="mx-auto max-w-4xl space-y-5 px-4 py-6">
      <Link
        to="/competitions"
        className="inline-flex min-h-11 items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Volver a competencias
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl text-charcoal">
            Revisión de identidad
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            Confirma si dos registros del histórico corresponden a la misma
            persona antes de cargar sus resultados.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={handleRebuild}
          disabled={rebuildMutation.isPending}
          data-testid="rebuild-candidates"
        >
          {rebuildMutation.isPending ? (
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw size={14} aria-hidden="true" />
          )}
          Recalcular candidatos
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p
          className="text-sm font-medium text-charcoal"
          data-testid="review-progress"
          aria-live="polite"
        >
          {totalCandidates > 0
            ? `${decided} de ${totalCandidates} decididos`
            : "Sin candidatos por revisar"}
        </p>
        <Select
          value={stateFilter}
          onValueChange={(value) => setStateFilter(value as StateFilterValue)}
        >
          <SelectTrigger className="w-56" aria-label="Filtrar por estado">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATE_FILTER_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {candidatesQuery.isLoading && (
        <div
          className="flex min-h-[30vh] items-center justify-center gap-2 text-sm text-mid-gray"
          role="status"
          aria-live="polite"
        >
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          Cargando candidatos...
        </div>
      )}

      {candidatesQuery.isError && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <AlertCircle size={24} className="text-red-600" aria-hidden="true" />
            <p className="text-sm text-charcoal">
              No se pudo cargar la revisión de identidad.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => candidatesQuery.refetch()}
            >
              Reintentar
            </Button>
          </CardContent>
        </Card>
      )}

      {!candidatesQuery.isLoading &&
        !candidatesQuery.isError &&
        items.length === 0 && (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
              <UserRoundX
                size={24}
                className="text-mid-gray"
                aria-hidden="true"
              />
              <p className="text-sm text-charcoal">
                {isPendingMode
                  ? "No hay candidatos pendientes de revisión."
                  : "No hay candidatos en este estado."}
              </p>
            </CardContent>
          </Card>
        )}

      {!candidatesQuery.isLoading &&
        !candidatesQuery.isError &&
        isPendingMode &&
        activeCandidate && (
          <DecisionCard
            candidate={activeCandidate}
            onDecide={handleDecide}
            isBusy={isBusy}
          />
        )}

      {!candidatesQuery.isLoading &&
        !candidatesQuery.isError &&
        !isPendingMode &&
        items.length > 0 && (
          <div className="space-y-3">
            {items.map((candidate) => (
              <CandidateRow
                key={candidate.id}
                candidate={candidate}
                onRequestUndo={setUndoTarget}
              />
            ))}
            {(hasPrevPage || hasNextPage) && (
              <div className="flex justify-between gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!hasPrevPage}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Anterior
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!hasNextPage}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Siguiente
                </Button>
              </div>
            )}
          </div>
        )}

      <AlertDialog
        open={undoTarget != null}
        onOpenChange={(open) => {
          if (!open) setUndoTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Deshacer esta decisión?</AlertDialogTitle>
            <AlertDialogDescription>
              {undoTarget && (
                <>
                  El candidato "{undoTarget.left.name_printed} —{" "}
                  {undoTarget.right.name_printed}" vuelve a quedar pendiente
                  de revisión.
                  {undoTarget.state === "same_person" &&
                    " Si sus resultados ya se cargaron, se separan de nuevo en dos competidores."}
                  {undoTarget.state === "different_people" &&
                    " Esto no une resultados ya cargados hasta que decidas de nuevo."}
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={reverseMutation.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                handleConfirmUndo();
              }}
              disabled={reverseMutation.isPending}
              data-testid="confirm-undo"
            >
              {reverseMutation.isPending ? "Deshaciendo..." : "Deshacer"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}

export default IdentityReviewPage;
