/**
 * RosterPanel — panel de convocatoria (roster) para una válida de Copa Valle.
 *
 * Funcionalidades:
 *   - Lista los convocados con nombre, estado (chip de color) y nota.
 *   - Selector de atleta del club para agregar nuevos convocados.
 *   - Cambio de estado inline por entrada (called_up → confirmed / withdrawn).
 *   - Eliminar entrada (con confirmación vía Dialog).
 *   - Bloque de reconciliación con badge ámbar cuando hay discrepancias.
 *   - Estados diseñados: loading / empty / error (FR-032).
 *
 * Acceso:
 *   - Coach/admin: lectura + escritura (agregar, editar, eliminar).
 *   - Padre: solo lectura de su propio hijo (el backend filtra antes de responder).
 *     El panel oculta los controles de edición cuando el usuario es padre.
 *
 * Props:
 *   - `raceEventId: number`   — ID del evento de carrera.
 *   - `isReadOnly?: boolean`  — si true, oculta todos los controles de edición.
 *                               El padre debe pasar true para respetar RBAC.
 */
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  UserCheck,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import {
  useCreateRosterEntry,
  useDeleteRosterEntry,
  useRaceRoster,
  useUpdateRosterEntry,
  getRosterErrorMessage,
} from "@/hooks/race/useRaceRoster";
import { cn } from "@/lib/utils";
import type { RosterEntry, RosterEntryStatus } from "@/types/raceRoster.types";

// ---------------------------------------------------------------------------
// Helpers de estilo por estado
// ---------------------------------------------------------------------------

const STATUS_VARIANT: Record<
  RosterEntryStatus,
  "default" | "success" | "secondary" | "warning"
> = {
  called_up: "default",
  confirmed: "success",
  withdrawn: "secondary",
};

const STATUS_LABELS: Record<RosterEntryStatus, string> = {
  called_up: "Convocado",
  confirmed: "Confirmado",
  withdrawn: "Retirado",
};

// ---------------------------------------------------------------------------
// Sub-componente: skeleton de carga
// ---------------------------------------------------------------------------

function RosterSkeleton() {
  return (
    <div
      className="space-y-2"
      role="status"
      aria-busy="true"
      aria-label="Cargando convocatoria"
    >
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: estado vacío
// ---------------------------------------------------------------------------

function EmptyRoster({ isReadOnly }: { isReadOnly: boolean }) {
  return (
    <div
      className="flex min-h-[16vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6 text-center ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="roster-panel-empty"
    >
      <Users size={32} className="text-mid-gray" aria-hidden="true" />
      <p className="text-sm font-medium text-charcoal">Sin convocados</p>
      <p className="text-xs text-mid-gray">
        {isReadOnly
          ? "No hay atletas convocados para esta válida."
          : "Agrega atletas del club a la convocatoria usando el buscador de arriba."}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: estado de error
// ---------------------------------------------------------------------------

function RosterError({
  onRetry,
  isFetching,
}: {
  onRetry: () => void;
  isFetching: boolean;
}) {
  return (
    <div
      className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
      role="alert"
      data-testid="roster-panel-error"
    >
      <AlertTriangle
        className="mt-0.5 h-5 w-5 shrink-0 text-red-500"
        aria-hidden="true"
      />
      <div className="flex-1 space-y-1">
        <p className="text-sm font-medium text-red-700">
          No se pudo cargar la convocatoria.
        </p>
        <p className="text-xs text-red-600">
          Verifica tu conexión y vuelve a intentarlo.
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={isFetching}
        className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        data-testid="roster-panel-retry"
      >
        {isFetching ? (
          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
        ) : (
          <RefreshCw size={14} aria-hidden="true" />
        )}
        Reintentar
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: banner de reconciliación
// ---------------------------------------------------------------------------

interface ReconciliationBannerProps {
  calledUpNoResult: number[];
  resultNotCalledUp: number[];
  entries: RosterEntry[];
}

function ReconciliationBanner({
  calledUpNoResult,
  resultNotCalledUp,
  entries,
}: ReconciliationBannerProps) {
  const hasDiscrepancies =
    calledUpNoResult.length > 0 || resultNotCalledUp.length > 0;

  if (!hasDiscrepancies) return null;

  // Construir mapeo athlete_id → nombre desde las entradas del roster
  const nameById: Record<number, string> = {};
  entries.forEach((e) => {
    nameById[e.athlete_id] = e.athlete_name;
  });

  return (
    <div
      className="rounded-xl border border-amber-200 bg-amber-50 p-4"
      role="note"
      aria-label="Discrepancias en la convocatoria"
      data-testid="roster-reconciliation-banner"
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle
          size={16}
          className="mt-0.5 shrink-0 text-amber-600"
          aria-hidden="true"
        />
        <div className="flex-1 space-y-2">
          <p className="text-sm font-semibold text-amber-900">
            Discrepancias con resultados importados
          </p>

          {calledUpNoResult.length > 0 && (
            <div data-testid="roster-called-up-no-result">
              <p className="mb-1 text-xs font-medium text-amber-800">
                Convocados sin resultado ({calledUpNoResult.length}):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {calledUpNoResult.map((id) => (
                  <Badge
                    key={id}
                    variant="warning"
                    className="text-xs"
                    data-testid={`reconciliation-no-result-${id}`}
                  >
                    {nameById[id] ?? `Atleta #${id}`}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {resultNotCalledUp.length > 0 && (
            <div data-testid="roster-result-not-called-up">
              <p className="mb-1 text-xs font-medium text-amber-800">
                Con resultado pero no convocados ({resultNotCalledUp.length}):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {resultNotCalledUp.map((id) => (
                  <Badge
                    key={id}
                    variant="warning"
                    className="text-xs"
                    data-testid={`reconciliation-not-called-up-${id}`}
                  >
                    Atleta #{id}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: selector de atleta para agregar
// ---------------------------------------------------------------------------

interface AddAthletePickerProps {
  raceEventId: number;
  alreadyInRoster: Set<number>;
}

function AddAthletePicker({
  raceEventId,
  alreadyInRoster,
}: AddAthletePickerProps) {
  const { data: athletesData, isLoading: athletesLoading } = useAthletes();
  const { mutate: createEntry, isPending, error } = useCreateRosterEntry();
  const [selectedId, setSelectedId] = useState<string>("");
  const [mutationError, setMutationError] = useState<string | null>(null);

  const availableAthletes = useMemo(
    () =>
      (athletesData?.items ?? []).filter(
        (a) => !alreadyInRoster.has(a.id),
      ),
    [athletesData, alreadyInRoster],
  );

  function handleAdd() {
    const athleteId = Number(selectedId);
    if (!athleteId) return;

    setMutationError(null);
    createEntry(
      { raceEventId, body: { athlete_id: athleteId, status: "called_up" } },
      {
        onSuccess: () => {
          setSelectedId("");
        },
        onError: (err) => {
          setMutationError(getRosterErrorMessage(err));
        },
      },
    );
  }

  return (
    <div className="space-y-2" data-testid="roster-add-picker">
      <div className="flex items-center gap-2">
        {/* Selector de atleta */}
        <div className="relative flex-1">
          <select
            id="roster-athlete-select"
            value={selectedId}
            onChange={(e) => {
              setSelectedId(e.target.value);
              setMutationError(null);
            }}
            disabled={athletesLoading || isPending}
            aria-label="Seleccionar atleta para convocar"
            className={cn(
              "h-11 w-full appearance-none rounded-lg border border-[rgba(34,42,53,0.12)]",
              "bg-white pl-3 pr-8 text-sm text-charcoal",
              "focus:outline-none focus:ring-2 focus:ring-primary/50",
              "disabled:opacity-50",
            )}
            data-testid="roster-athlete-select"
          >
            <option value="">
              {athletesLoading ? "Cargando atletas…" : "Seleccionar atleta…"}
            </option>
            {availableAthletes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.first_name} {a.last_name}
              </option>
            ))}
            {availableAthletes.length === 0 && !athletesLoading && (
              <option value="" disabled>
                Todos los atletas ya están convocados
              </option>
            )}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-mid-gray"
            aria-hidden="true"
          />
        </div>

        {/* Botón agregar */}
        <Button
          type="button"
          size="default"
          disabled={!selectedId || isPending}
          onClick={handleAdd}
          data-testid="roster-add-btn"
          aria-label="Agregar atleta a la convocatoria"
        >
          {isPending ? (
            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          ) : (
            <Plus size={16} aria-hidden="true" />
          )}
          <span className="hidden sm:inline">Agregar</span>
        </Button>
      </div>

      {/* Error de mutación */}
      {(mutationError ?? (error ? getRosterErrorMessage(error) : null)) && (
        <p
          className="text-xs text-red-600"
          role="alert"
          data-testid="roster-add-error"
        >
          {mutationError ?? getRosterErrorMessage(error)}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: fila de entrada del roster
// ---------------------------------------------------------------------------

interface RosterRowProps {
  entry: RosterEntry;
  raceEventId: number;
  isReadOnly: boolean;
  onDeleteRequest: (entry: RosterEntry) => void;
}

function RosterRow({
  entry,
  raceEventId,
  isReadOnly,
  onDeleteRequest,
}: RosterRowProps) {
  const { mutate: updateEntry, isPending: isUpdating } =
    useUpdateRosterEntry();
  const [updateError, setUpdateError] = useState<string | null>(null);

  function handleStatusChange(newStatus: RosterEntryStatus) {
    setUpdateError(null);
    updateEntry(
      { raceEventId, entryId: entry.id, body: { status: newStatus } },
      {
        onError: (err) => {
          setUpdateError(getRosterErrorMessage(err));
        },
      },
    );
  }

  return (
    <TableRow data-testid={`roster-entry-${entry.id}`}>
      {/* Nombre */}
      <TableCell>
        <div className="flex items-center gap-2">
          <div
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-charcoal text-[11px] font-bold text-white"
            aria-hidden="true"
          >
            {entry.athlete_name
              .split(" ")
              .slice(0, 2)
              .map((w) => w[0] ?? "")
              .join("")
              .toUpperCase() || <UserCheck size={12} />}
          </div>
          <div>
            <p className="text-sm font-medium text-charcoal">
              {entry.athlete_name}
            </p>
            {entry.note && (
              <p className="text-xs text-mid-gray">{entry.note}</p>
            )}
            {updateError && (
              <p className="text-xs text-red-500" role="alert">
                {updateError}
              </p>
            )}
          </div>
        </div>
      </TableCell>

      {/* Estado */}
      <TableCell className="w-36">
        {isReadOnly ? (
          <Badge variant={STATUS_VARIANT[entry.status]} className="text-xs">
            {STATUS_LABELS[entry.status]}
          </Badge>
        ) : (
          <div className="relative inline-block">
            <select
              value={entry.status}
              onChange={(e) =>
                handleStatusChange(e.target.value as RosterEntryStatus)
              }
              disabled={isUpdating}
              aria-label={`Cambiar estado de ${entry.athlete_name}`}
              className={cn(
                "h-8 appearance-none rounded-lg border border-[rgba(34,42,53,0.12)]",
                "bg-white pl-2.5 pr-7 text-xs text-charcoal",
                "focus:outline-none focus:ring-2 focus:ring-primary/50",
                "disabled:opacity-50",
                entry.status === "confirmed" && "border-green-200 bg-green-50 text-green-800",
                entry.status === "withdrawn" && "bg-light-gray text-mid-gray",
              )}
              data-testid={`roster-status-select-${entry.id}`}
            >
              <option value="called_up">Convocado</option>
              <option value="confirmed">Confirmado</option>
              <option value="withdrawn">Retirado</option>
            </select>
            <ChevronDown
              size={12}
              className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-mid-gray"
              aria-hidden="true"
            />
            {isUpdating && (
              <Loader2
                size={12}
                className="absolute right-7 top-1/2 -translate-y-1/2 animate-spin text-primary"
                aria-hidden="true"
              />
            )}
          </div>
        )}
      </TableCell>

      {/* Acciones (solo coach/admin) */}
      {!isReadOnly && (
        <TableCell className="w-12 text-right">
          <button
            type="button"
            onClick={() => onDeleteRequest(entry)}
            aria-label={`Eliminar a ${entry.athlete_name} de la convocatoria`}
            className="rounded-lg p-1.5 text-mid-gray transition-colors hover:bg-red-50 hover:text-red-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            data-testid={`roster-delete-btn-${entry.id}`}
          >
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </TableCell>
      )}
    </TableRow>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RosterPanelProps {
  raceEventId: number;
  /** Si true, solo muestra los datos sin controles de edición (para padres). */
  isReadOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Component principal
// ---------------------------------------------------------------------------

export function RosterPanel({
  raceEventId,
  isReadOnly = false,
}: RosterPanelProps) {
  const { data, isLoading, isError, isFetching, refetch } =
    useRaceRoster(raceEventId);
  const { mutate: deleteEntry, isPending: isDeleting } =
    useDeleteRosterEntry();

  // Diálogo de confirmación de eliminación
  const [deleteTarget, setDeleteTarget] = useState<RosterEntry | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Conjunto de athlete_ids ya en el roster (para el picker)
  const alreadyInRoster = useMemo<Set<number>>(
    () => new Set(data?.entries.map((e) => e.athlete_id) ?? []),
    [data],
  );

  function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleteError(null);

    deleteEntry(
      { raceEventId, entryId: deleteTarget.id },
      {
        onSuccess: () => {
          setDeleteTarget(null);
        },
        onError: (err) => {
          setDeleteError(getRosterErrorMessage(err));
        },
      },
    );
  }

  // ── Cargando ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div
        className="space-y-4 rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
        data-testid="roster-panel"
      >
        <RosterSkeleton />
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (isError || !data) {
    return (
      <div
        className="space-y-4"
        data-testid="roster-panel"
      >
        <RosterError
          onRetry={() => void refetch()}
          isFetching={isFetching}
        />
      </div>
    );
  }

  const { entries, reconciliation } = data;

  return (
    <div
      className="space-y-4"
      data-testid="roster-panel"
    >
      {/* Encabezado con contador */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-charcoal">
            Convocatoria
          </h3>
          {entries.length > 0 && (
            <Badge variant="secondary" className="text-xs" data-testid="roster-count-badge">
              {entries.length}{" "}
              {entries.length === 1 ? "atleta" : "atletas"}
            </Badge>
          )}
        </div>
      </div>

      {/* Selector para agregar (solo coach/admin) */}
      {!isReadOnly && (
        <AddAthletePicker
          raceEventId={raceEventId}
          alreadyInRoster={alreadyInRoster}
        />
      )}

      {/* Banner de reconciliación */}
      <ReconciliationBanner
        calledUpNoResult={reconciliation.called_up_no_result}
        resultNotCalledUp={reconciliation.result_not_called_up}
        entries={entries}
      />

      {/* Lista de convocados */}
      {entries.length === 0 ? (
        <EmptyRoster isReadOnly={isReadOnly} />
      ) : (
        <div
          className="overflow-hidden rounded-xl bg-white ring-1 ring-[rgba(34,42,53,0.08)]"
          data-testid="roster-entries-table"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Atleta</TableHead>
                <TableHead>Estado</TableHead>
                {!isReadOnly && <TableHead className="sr-only">Acciones</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <RosterRow
                  key={entry.id}
                  entry={entry}
                  raceEventId={raceEventId}
                  isReadOnly={isReadOnly}
                  onDeleteRequest={setDeleteTarget}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Diálogo de confirmación de eliminación */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
      >
        <DialogContent data-testid="roster-delete-dialog">
          <DialogHeader>
            <DialogTitle>Retirar de la convocatoria</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <p className="text-sm text-charcoal">
              ¿Confirmas retirar a{" "}
              <strong>{deleteTarget?.athlete_name}</strong> de la convocatoria?
            </p>
            {deleteError && (
              <p
                className="mt-2 text-xs text-red-600"
                role="alert"
                data-testid="roster-delete-error"
              >
                {deleteError}
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setDeleteTarget(null);
                setDeleteError(null);
              }}
              disabled={isDeleting}
              data-testid="roster-delete-cancel"
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDeleteConfirm}
              disabled={isDeleting}
              data-testid="roster-delete-confirm"
            >
              {isDeleting ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 size={14} aria-hidden="true" />
              )}
              Retirar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
