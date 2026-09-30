import { useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import {
  AnthropometryCapture,
  type CaptureResult,
} from "@/components/athletes/anthropometry-capture/AnthropometryCapture";
import { ErrorState } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { RouteFallback } from "@/components/shared/RouteFallback";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  ANTHROPOMETRY_ROSTER_KEY,
  useAnthropometryRoster,
} from "@/hooks/athletes/useAnthropometry";
import { skinfoldCapturePath } from "@/lib/bodyComposition/eligibility";
import { cn } from "@/lib/utils";
import { todayISO } from "@/schemas/anthropometryCapture.schema";
import { useMeasurementSessionStore } from "@/store/measurementSession.store";
import type { RosterRow } from "@/types/anthropometry.types";
import type { Sex } from "@/types/enums";

/**
 * MeasurementSessionPage — `/anthropometry/session` (feature 048, US3, T045).
 * Coach/admin únicamente (guard en `App.tsx`).
 *
 * Tres vistas guiadas por `measurementSession.store` (solo memoria):
 *  1. Selección: fecha, categorías, tarjetas con «Medido hoy».
 *  2. Cola: «3 de 12», deportista actual y `AnthropometryCapture` con la
 *     fecha bloqueada a la de la jornada.
 *  3. Resumen: Medidos / Omitidos / Pendientes y «Terminar jornada».
 *
 * Recargar pierde la jornada (clarificación 1). Los nombres salen del roster
 * (TanStack Query), nunca del store; la fecha de nacimiento solo viaja a la
 * captura para calcular edad y no se muestra.
 */

export const SESSION_PATH = "/anthropometry/session";

const ALL_CATEGORIES = "__all__";

const CHIP_CLASSES =
  "min-h-12 rounded-full border border-border-gray px-4 text-sm font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-surface";

/** YYYY-MM-DD → dd/mm/aaaa sin pasar por `Date` (evita el corrimiento UTC). */
function formatIsoDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function skinfoldsFromSessionPath(athleteId: number, recordId: number): string {
  return `${skinfoldCapturePath(athleteId, recordId)}?returnTo=${SESSION_PATH}`;
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function MeasurementSessionPage() {
  const sessionDate = useMeasurementSessionStore((s) => s.date);
  const currentId = useMeasurementSessionStore((s) => s.currentId);
  const [showSummary, setShowSummary] = useState(false);

  const view = sessionDate === null ? "picker" : showSummary || currentId === null ? "summary" : "queue";

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Jornada de medición"
        subtitle={
          sessionDate
            ? `Medición del ${formatIsoDate(sessionDate)}`
            : "Mide a varios deportistas seguidos en la misma fecha."
        }
        backTo={{ to: "/athletes", label: "Volver a atletas" }}
      />
      {view === "picker" && <PickerView />}
      {view === "queue" && sessionDate && (
        <QueueView date={sessionDate} onShowSummary={() => setShowSummary(true)} />
      )}
      {view === "summary" && sessionDate && (
        <SummaryView date={sessionDate} onResume={() => setShowSummary(false)} />
      )}
    </div>
  );
}

export default MeasurementSessionPage;

// ---------------------------------------------------------------------------
// 1. Selección
// ---------------------------------------------------------------------------

function PickerView() {
  const start = useMeasurementSessionStore((s) => s.start);
  const id = useId();
  const [date, setDate] = useState(() => todayISO());
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());

  const isFuture = date > todayISO();
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(date) && !isFuture;
  const roster = useAnthropometryRoster(date, validDate);

  const rows = useMemo(() => roster.data ?? [], [roster.data]);
  const categories = useMemo(
    () => Array.from(new Set(rows.map((r) => r.category))).sort((a, b) => a.localeCompare(b, "es")),
    [rows],
  );
  const visible = useMemo(
    () => (category === ALL_CATEGORIES ? rows : rows.filter((r) => r.category === category)),
    [rows, category],
  );
  // Solo cuentan los seleccionados que existen en el roster de esta fecha.
  const selectedIds = rows.filter((r) => selected.has(r.athlete_id)).map((r) => r.athlete_id);

  const toggle = (athleteId: number, checked: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(athleteId);
      else next.delete(athleteId);
      return next;
    });

  const selectAllVisible = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      // Los ya medidos en la fecha no se agregan en bloque: darían 409.
      for (const r of visible) if (!r.has_record_on_date) next.add(r.athlete_id);
      return next;
    });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline sm:p-6">
        <div className="flex flex-col gap-1.5 sm:max-w-xs">
          <Label htmlFor={`${id}-date`}>Fecha de la medición</Label>
          <Input
            id={`${id}-date`}
            type="date"
            value={date}
            max={todayISO()}
            aria-invalid={isFuture ? true : undefined}
            aria-describedby={isFuture ? `${id}-date-error` : undefined}
            onChange={(event) => setDate(event.target.value)}
          />
          {isFuture && (
            <p id={`${id}-date-error`} className="text-xs text-danger">
              No puede ser futura
            </p>
          )}
        </div>

        {categories.length > 0 && (
          <div className="flex flex-col gap-2">
            <span id={`${id}-cat`} className="text-sm font-medium text-charcoal">
              Categoría
            </span>
            <ToggleGroup
              type="single"
              value={category}
              onValueChange={(value) => setCategory(value || ALL_CATEGORIES)}
              aria-labelledby={`${id}-cat`}
              className="flex flex-wrap justify-start gap-2"
            >
              <ToggleGroupItem value={ALL_CATEGORIES} className={CHIP_CLASSES}>
                Todas
              </ToggleGroupItem>
              {categories.map((c) => (
                <ToggleGroupItem key={c} value={c} className={CHIP_CLASSES}>
                  {c}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        )}
      </div>

      {roster.isLoading && validDate && <RouteFallback label="Cargando deportistas..." />}
      {roster.isError && (
        <ErrorState
          message="No se pudo cargar la lista de deportistas."
          onRetry={() => void roster.refetch()}
        />
      )}

      {roster.isSuccess && rows.length === 0 && (
        <p className="text-sm text-mid-gray">No hay deportistas activos para medir.</p>
      )}

      {roster.isSuccess && visible.length > 0 && (
        <>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-mid-gray" aria-live="polite">
              {selectedIds.length} seleccionados
            </p>
            <Button
              type="button"
              variant="secondary"
              size="lg"
              className="w-full sm:w-auto"
              onClick={selectAllVisible}
            >
              Seleccionar todos los visibles
            </Button>
          </div>

          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-label="Deportistas">
            {visible.map((row) => (
              <RosterCard
                key={row.athlete_id}
                row={row}
                checked={selected.has(row.athlete_id)}
                onCheckedChange={(checked) => toggle(row.athlete_id, checked)}
              />
            ))}
          </ul>
        </>
      )}

      <div className="sticky bottom-0 -mx-4 border-t border-hairline bg-surface px-4 py-3 sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
        <Button
          type="button"
          size="lg"
          className="w-full sm:w-auto"
          disabled={selectedIds.length === 0 || !validDate || !roster.isSuccess}
          onClick={() => start(date, selectedIds)}
        >
          Empezar jornada ({selectedIds.length})
        </Button>
      </div>
    </div>
  );
}

function RosterCard({
  row,
  checked,
  onCheckedChange,
}: {
  row: RosterRow;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <li>
      <label
        htmlFor={`${id}-cb`}
        className={cn(
          "flex min-h-12 cursor-pointer items-start gap-3 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline transition-colors",
          checked && "ring-2 ring-charcoal",
        )}
      >
        <Checkbox
          id={`${id}-cb`}
          className="mt-0.5"
          checked={checked}
          onCheckedChange={(value) => onCheckedChange(value === true)}
          aria-labelledby={`${id}-name`}
          aria-describedby={`${id}-meta`}
        />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            <span id={`${id}-name`} className="break-words font-medium text-charcoal">
              {row.full_name}
            </span>
            {row.has_record_on_date && <Badge variant="success">Medido hoy</Badge>}
          </span>
          <span id={`${id}-meta`} className="text-sm text-mid-gray">
            {row.category} ·{" "}
            {row.last_evaluation_date
              ? `Última medición: ${formatIsoDate(row.last_evaluation_date)}`
              : "Sin mediciones"}
          </span>
        </span>
      </label>
    </li>
  );
}

// ---------------------------------------------------------------------------
// 2. Cola
// ---------------------------------------------------------------------------

interface LastSaved {
  athleteId: number;
  recordId: number;
  name: string;
  skinfoldsEligible: boolean;
}

function QueueView({ date, onShowSummary }: { date: string; onShowSummary: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const athleteIds = useMeasurementSessionStore((s) => s.athleteIds);
  const statusById = useMeasurementSessionStore((s) => s.statusById);
  const currentId = useMeasurementSessionStore((s) => s.currentId);
  const markMeasured = useMeasurementSessionStore((s) => s.markMeasured);
  const skip = useMeasurementSessionStore((s) => s.skip);
  const goTo = useMeasurementSessionStore((s) => s.goTo);

  const roster = useAnthropometryRoster(date);
  const [lastSaved, setLastSaved] = useState<LastSaved | null>(null);
  const [listOpen, setListOpen] = useState(false);

  const rowsById = useMemo(
    () => new Map((roster.data ?? []).map((r) => [r.athlete_id, r])),
    [roster.data],
  );

  if (roster.isLoading) return <RouteFallback label="Cargando jornada..." />;
  if (roster.isError) {
    return (
      <ErrorState
        message="No se pudo cargar la lista de deportistas."
        onRetry={() => void roster.refetch()}
      />
    );
  }

  const total = athleteIds.length;
  const done = athleteIds.filter((id) => statusById[id] !== "pending").length;
  const position = Math.min(done + 1, total);
  const row = currentId !== null ? rowsById.get(currentId) : undefined;

  const handleDone = (athleteId: number, current: RosterRow) => (result: CaptureResult) => {
    const hasWarnings = (result.record?.plausibility_flags?.length ?? 0) > 0;
    toast.success("Guardado");
    markMeasured(athleteId, result.recordId, hasWarnings);
    void queryClient.invalidateQueries({ queryKey: [ANTHROPOMETRY_ROSTER_KEY] });
    if (result.intent === "skinfolds") {
      navigate(skinfoldsFromSessionPath(athleteId, result.recordId));
      return;
    }
    setLastSaved({
      athleteId,
      recordId: result.recordId,
      name: current.full_name,
      skinfoldsEligible: current.skinfolds_eligible,
    });
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-charcoal">
          {position} de {total}
        </p>
        <div
          role="progressbar"
          aria-label="Avance de la jornada"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-valuetext={`${done} de ${total} listos`}
          className="h-2 w-full overflow-hidden rounded-full bg-light-gray"
        >
          <div
            className="h-full rounded-full bg-primary transition-[width]"
            style={{ width: `${total ? (done / total) * 100 : 0}%` }}
          />
        </div>
      </div>

      {lastSaved && (
        <div
          role="status"
          className="flex flex-col gap-3 rounded-card bg-success/10 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-sm text-charcoal">Guardado: {lastSaved.name}.</p>
          {lastSaved.skinfoldsEligible && (
            <Link
              to={skinfoldsFromSessionPath(lastSaved.athleteId, lastSaved.recordId)}
              className={cn(buttonVariants({ variant: "outline", size: "lg" }), "w-full sm:w-auto")}
            >
              Agregar pliegues
            </Link>
          )}
        </div>
      )}

      {currentId !== null && row ? (
        <section
          aria-labelledby="session-current-athlete"
          className="flex flex-col gap-4 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline sm:p-6"
        >
          <div className="flex flex-col gap-0.5">
            <h2
              id="session-current-athlete"
              className="break-words font-display text-lg text-charcoal"
            >
              {row.full_name}
            </h2>
            <p className="text-sm text-mid-gray">{row.category}</p>
          </div>
          <AnthropometryCapture
            key={currentId}
            // El roster usa los mismos literales "M" | "F" que el enum `Sex`.
            athlete={{ id: row.athlete_id, sex: row.sex as Sex, birth_date: row.birth_date }}
            lockedDate={date}
            allowSkinfoldsExit={row.skinfolds_eligible}
            onDone={handleDone(row.athlete_id, row)}
            onOpenExisting={(recordId) => {
              // Ya estaba medido en la fecha de la jornada: queda en «Medidos»
              // y el resumen enlaza a esa medición para revisarla.
              markMeasured(row.athlete_id, recordId, false);
              toast.info("Ya tenía una medición en esta fecha. Quedó en «Medidos».");
            }}
          />
        </section>
      ) : (
        <p role="alert" className="text-sm text-charcoal">
          No encontramos a este deportista en la lista de la fecha. Omítelo para seguir.
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          type="button"
          variant="secondary"
          size="lg"
          className="w-full sm:w-auto"
          disabled={currentId === null}
          onClick={() => {
            if (currentId !== null) {
              setLastSaved(null);
              skip(currentId);
            }
          }}
        >
          Omitir por hoy
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="lg"
          className="w-full sm:w-auto"
          onClick={() => setListOpen(true)}
        >
          Ver lista
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="lg"
          className="w-full sm:w-auto"
          onClick={onShowSummary}
        >
          Ver resumen
        </Button>
      </div>

      <SessionListSheet
        open={listOpen}
        onOpenChange={setListOpen}
        rowsById={rowsById}
        onJump={(id) => {
          setLastSaved(null);
          goTo(id);
          setListOpen(false);
        }}
      />
    </div>
  );
}

function SessionListSheet({
  open,
  onOpenChange,
  rowsById,
  onJump,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rowsById: Map<number, RosterRow>;
  onJump: (id: number) => void;
}) {
  const athleteIds = useMeasurementSessionStore((s) => s.athleteIds);
  const statusById = useMeasurementSessionStore((s) => s.statusById);
  const currentId = useMeasurementSessionStore((s) => s.currentId);
  const nameOf = (id: number) => rowsById.get(id)?.full_name ?? "Deportista";

  const groups = [
    { title: "Pendientes", status: "pending" as const },
    { title: "Omitidos", status: "skipped" as const },
    { title: "Medidos", status: "measured" as const },
  ];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        className="max-h-[85dvh] sm:mx-auto sm:max-w-lg sm:rounded-t-card"
      >
        <SheetHeader>
          <SheetTitle>Lista de la jornada</SheetTitle>
          <SheetDescription>Toca un pendiente u omitido para medirlo.</SheetDescription>
        </SheetHeader>
        <SheetBody className="flex flex-col gap-5">
          {groups.map(({ title, status }) => {
            const ids = athleteIds.filter((id) => statusById[id] === status);
            return (
              <section key={status} className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold text-charcoal">
                  {title} ({ids.length})
                </h3>
                {ids.length === 0 ? (
                  <p className="text-sm text-mid-gray">Ninguno.</p>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {ids.map((id) => (
                      <li key={id}>
                        {status === "measured" ? (
                          <p className="px-3 py-2 text-sm text-charcoal">{nameOf(id)}</p>
                        ) : (
                          <Button
                            type="button"
                            variant="ghost"
                            size="lg"
                            className="w-full justify-start"
                            aria-current={id === currentId ? "true" : undefined}
                            onClick={() => onJump(id)}
                          >
                            {nameOf(id)}
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// 3. Resumen
// ---------------------------------------------------------------------------

function SummaryView({ date, onResume }: { date: string; onResume: () => void }) {
  const queryClient = useQueryClient();
  const athleteIds = useMeasurementSessionStore((s) => s.athleteIds);
  const statusById = useMeasurementSessionStore((s) => s.statusById);
  const recordIdById = useMeasurementSessionStore((s) => s.recordIdById);
  const warningsById = useMeasurementSessionStore((s) => s.warningsById);
  const reopen = useMeasurementSessionStore((s) => s.reopen);
  const goTo = useMeasurementSessionStore((s) => s.goTo);
  const reset = useMeasurementSessionStore((s) => s.reset);

  const roster = useAnthropometryRoster(date);
  const nameOf = (id: number) =>
    roster.data?.find((r) => r.athlete_id === id)?.full_name ?? "Deportista";

  const measured = athleteIds.filter((id) => statusById[id] === "measured");
  const skipped = athleteIds.filter((id) => statusById[id] === "skipped");
  const pending = athleteIds.filter((id) => statusById[id] === "pending");

  const itemClasses =
    "flex flex-col gap-2 rounded-card bg-surface-raised p-3 ring-1 ring-hairline sm:flex-row sm:items-center sm:justify-between";

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-display text-lg text-charcoal">Resumen de la jornada</h2>

      <section aria-labelledby="summary-measured" className="flex flex-col gap-2">
        <h3 id="summary-measured" className="text-base font-semibold text-charcoal">
          Medidos ({measured.length})
        </h3>
        {measured.length === 0 ? (
          <p className="text-sm text-mid-gray">Ninguno.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {measured.map((id) => (
              <li key={id} className={itemClasses}>
                <Link
                  to={`/athletes/${id}/anthropometry/${recordIdById[id]}/edit`}
                  className="inline-flex min-h-12 items-center break-words font-medium text-link-blue underline"
                >
                  {nameOf(id)}
                </Link>
                {warningsById[id] && (
                  <Badge variant="warning" className="self-start sm:self-auto">
                    Revisar
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="summary-skipped" className="flex flex-col gap-2">
        <h3 id="summary-skipped" className="text-base font-semibold text-charcoal">
          Omitidos ({skipped.length})
        </h3>
        {skipped.length === 0 ? (
          <p className="text-sm text-mid-gray">Ninguno.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {skipped.map((id) => (
              <li key={id} className={itemClasses}>
                <span className="break-words text-charcoal">{nameOf(id)}</span>
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  className="w-full sm:w-auto"
                  aria-label={`Medir ahora a ${nameOf(id)}`}
                  onClick={() => {
                    reopen(id);
                    onResume();
                  }}
                >
                  Medir ahora
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="summary-pending" className="flex flex-col gap-2">
        <h3 id="summary-pending" className="text-base font-semibold text-charcoal">
          Pendientes ({pending.length})
        </h3>
        {pending.length === 0 ? (
          <p className="text-sm text-mid-gray">Ninguno.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {pending.map((id) => (
              <li key={id} className={itemClasses}>
                <span className="break-words text-charcoal">{nameOf(id)}</span>
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  className="w-full sm:w-auto"
                  aria-label={`Medir ahora a ${nameOf(id)}`}
                  onClick={() => {
                    goTo(id);
                    onResume();
                  }}
                >
                  Medir ahora
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Button
        type="button"
        size="lg"
        className="w-full sm:w-auto sm:self-start"
        onClick={() => {
          reset();
          onResume();
          void queryClient.invalidateQueries({ queryKey: [ANTHROPOMETRY_ROSTER_KEY] });
        }}
      >
        Terminar jornada
      </Button>
    </div>
  );
}
