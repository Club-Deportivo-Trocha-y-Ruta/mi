/**
 * AthleteNewslettersDashboardPage — panel de control de boletines mensuales.
 *
 * Coach selecciona mes/año y ve el grid de atletas del club con el estado de su
 * boletín. Desde aquí puede generar todos los boletines en batch o navegar al
 * detalle de un atleta.
 *
 * Path: /training/athlete-newsletters
 * Roles: coach, admin
 */

import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { FileText, Loader2, Play, RefreshCw } from "lucide-react";

import {
  useBatchCreateNewsletters,
  useGenerateNewsletter,
  parseApiError,
} from "@/api/athleteNewsletters";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import {
  useNewsletterStatusSummary,
  type NewsletterStatusSummaryItem,
} from "@/hooks/training/useNewsletterStatusSummary";
import { useAuthStore } from "@/store/auth.store";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogBody,
  DialogFooter,
} from "@/components/ui/dialog";
import { formatDayMonthShort } from "@/lib/datetime";
import type { NewsletterStatus } from "@/types/athleteNewsletter.types";
import type { AthleteOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const STATUS_CONFIG: Record<
  NewsletterStatus | "none",
  { label: string; badgeClass: string }
> = {
  none: { label: "Sin generar", badgeClass: "bg-gray-100 text-gray-500 border border-gray-200" },
  draft: { label: "Borrador", badgeClass: "bg-yellow-100 text-yellow-700 border border-yellow-300" },
  approved: { label: "Aprobado", badgeClass: "bg-green-100 text-green-700 border border-green-300" },
  sent: { label: "Enviado", badgeClass: "bg-blue-100 text-blue-700 border border-blue-300" },
  failed: { label: "Fallido", badgeClass: "bg-red-100 text-red-700 border border-red-300" },
};

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

// ---------------------------------------------------------------------------
// Athlete card
// ---------------------------------------------------------------------------

interface AthleteNewsletterCardProps {
  athlete: AthleteOut;
  year: number;
  month: number;
  /**
   * Entrada del resumen para este atleta (undefined = "Sin generar" para el
   * período seleccionado). Viene de useNewsletterStatusSummary, resuelto por
   * el padre — la card ya NO hace fetch propio (ver AthleteCardWithFilter).
   */
  newsletter: NewsletterStatusSummaryItem | undefined;
  onClick: (athleteId: number, newsletterId?: number) => void;
}

function AthleteNewsletterCard({
  athlete,
  year,
  month,
  newsletter,
  onClick,
}: AthleteNewsletterCardProps) {
  const status: NewsletterStatus | "none" = newsletter?.status ?? "none";
  const config = STATUS_CONFIG[status];

  const queryClient = useQueryClient();
  const generateMutation = useGenerateNewsletter(athlete.id);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const isNone = status === "none";
  const canRegenerate = status === "draft" || status === "failed";

  /**
   * El resumen del dashboard vive en la queryKey "newsletter-status-summary"
   * (useNewsletterStatusSummary), NO en "athlete-newsletters" — que es lo
   * único que useGenerateNewsletter invalida por defecto. Sin esto, el badge
   * de la card se quedaría desactualizado tras generar/regenerar hasta el
   * próximo refetch natural.
   */
  function invalidateSummary() {
    void queryClient.invalidateQueries({ queryKey: ["newsletter-status-summary"] });
  }

  function handleGenerate(e: React.MouseEvent) {
    e.stopPropagation();
    setActionError(null);
    generateMutation.mutate(
      { year, month, force: false },
      {
        onSuccess: invalidateSummary,
        onError: (err) =>
          setActionError(parseApiError(err, "Error al generar el boletín.")),
      },
    );
  }

  function handleRegenerateConfirm() {
    setShowRegenerateConfirm(false);
    setActionError(null);
    generateMutation.mutate(
      { year, month, force: true },
      {
        onSuccess: invalidateSummary,
        onError: (err) =>
          setActionError(parseApiError(err, "Error al regenerar el boletín.")),
      },
    );
  }

  return (
    <>
      <div
        className="rounded-xl bg-white p-4 transition-shadow hover:shadow-md"
        style={cardStyle}
        data-testid={`athlete-card-${athlete.id}`}
      >
        {/* Clickable area — navigate to detail */}
        <button
          type="button"
          onClick={() => onClick(athlete.id, newsletter?.newsletter_id)}
          className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 rounded-lg"
          aria-label={`Ver boletín de ${athlete.first_name} ${athlete.last_name}: ${config.label}`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium text-charcoal">
                {athlete.first_name} {athlete.last_name}
              </p>
              <p className="text-xs text-mid-gray mt-0.5">
                {athlete.category ?? "Sin categoría"}{" "}
                {athlete.age_decimal ? `· ${Math.floor(athlete.age_decimal)} años` : ""}
              </p>
            </div>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${config.badgeClass}`}
              data-testid={`status-badge-${athlete.id}`}
            >
              {config.label}
            </span>
          </div>

          {/*
            error_message NO viene en el resumen liviano (NewsletterStatusSummaryItem):
            el badge "Fallido" ya señala el estado; el detalle del error se
            consulta en la vista de detalle del atleta (useAthleteNewsletter).
          */}

          {newsletter?.sent_at && (
            <p className="mt-1 text-xs text-mid-gray">
              Enviado el {formatDayMonthShort(newsletter.sent_at)}
            </p>
          )}
        </button>

        {/* Action error */}
        {actionError && (
          <p className="mt-2 text-xs text-red-600" role="alert">{actionError}</p>
        )}

        {/* Action buttons */}
        {(isNone || canRegenerate) && (
          <div className="mt-3 flex gap-2">
            {isNone && (
              <button
                type="button"
                onClick={handleGenerate}
                disabled={generateMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-80 disabled:opacity-50"
                data-testid={`generate-btn-${athlete.id}`}
                aria-label={`Generar boletín para ${athlete.first_name} ${athlete.last_name}`}
              >
                {generateMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                ) : (
                  <Play className="h-3 w-3" aria-hidden="true" />
                )}
                {generateMutation.isPending ? "Generando…" : "Generar"}
              </button>
            )}
            {canRegenerate && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setShowRegenerateConfirm(true); }}
                disabled={generateMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid={`regenerate-btn-${athlete.id}`}
                aria-label={`Regenerar boletín de ${athlete.first_name} ${athlete.last_name}`}
              >
                <RefreshCw className="h-3 w-3" aria-hidden="true" />
                Regenerar
              </button>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={showRegenerateConfirm}
        title="Regenerar boletín"
        description="Se borrará la narrativa actual y se generará una nueva. La narrativa editada se perderá. ¿Continuar?"
        confirmLabel="Sí, regenerar"
        cancelLabel="Cancelar"
        tone="default"
        isPending={generateMutation.isPending}
        onCancel={() => setShowRegenerateConfirm(false)}
        onConfirm={handleRegenerateConfirm}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Batch progress modal
// ---------------------------------------------------------------------------

interface BatchModalProps {
  open: boolean;
  onClose: () => void;
  year: number;
  month: number;
  clubId: number;
}

function BatchModal({ open, onClose, year, month, clubId }: BatchModalProps) {
  const batchMutation = useBatchCreateNewsletters(clubId);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [forceGenerate, setForceGenerate] = useState(false);

  function handleGenerate() {
    setError(null);
    batchMutation.mutate(
      { year, month, force: forceGenerate },
      {
        onSuccess: () => {
          // Modal stays open to show result summary. Refresca el resumen del
          // dashboard para que el grid muestre los boletines recién creados.
          void queryClient.invalidateQueries({ queryKey: ["newsletter-status-summary"] });
        },
        onError: (err) => {
          if (isAxiosError(err)) {
            setError(
              err.response?.data?.detail ??
                "Error al generar los boletines. Intenta de nuevo.",
            );
          } else {
            setError("Error inesperado. Intenta de nuevo.");
          }
        },
      },
    );
  }

  function handleClose() {
    batchMutation.reset();
    setError(null);
    setForceGenerate(false);
    onClose();
  }

  const result = batchMutation.data;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generar boletines del mes</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <p className="text-sm text-charcoal">
            Se generarán boletines para todos los atletas activos del club para{" "}
            <span className="font-semibold">
              {MONTH_NAMES[month - 1]} {year}
            </span>
            .
          </p>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
            <input
              type="checkbox"
              checked={forceGenerate}
              onChange={(e) => setForceGenerate(e.target.checked)}
              className="h-4 w-4 rounded border-mid-gray accent-charcoal"
              disabled={batchMutation.isPending || !!result}
            />
            Generar incluso para el mes actual
          </label>

          {error && (
            <p
              className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              {error}
            </p>
          )}

          {/* Resultado del batch */}
          {result && (
            <div
              className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 space-y-1"
              role="status"
              data-testid="batch-result"
            >
              <p className="text-sm font-semibold text-green-800">
                Proceso completado
              </p>
              <p className="text-sm text-green-700">
                Creados: <span className="font-medium">{result.created}</span>{" "}
                · Omitidos: <span className="font-medium">{result.skipped}</span>{" "}
                · Fallidos: <span className="font-medium">{result.failed}</span>
              </p>
              {result.errors.length > 0 && (
                <ul className="mt-1 space-y-0.5" role="list">
                  {result.errors.map((e, i) => (
                    <li key={i} className="text-xs text-red-700">
                      {e}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </DialogBody>
        <DialogFooter>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            {result ? "Cerrar" : "Cancelar"}
          </button>
          {!result && (
            <button
              type="button"
              onClick={handleGenerate}
              disabled={batchMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              data-testid="batch-generate-btn"
            >
              {batchMutation.isPending && (
                <svg
                  className="h-4 w-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v8H4z"
                  />
                </svg>
              )}
              Generar para todos
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function AthleteNewslettersDashboardPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clubId = user?.club_ids?.[0];

  // Boletines solo cubren meses ya finalizados → arrancar en mes anterior al actual.
  const initialPeriod = useMemo(() => {
    const now = new Date();
    const m = now.getMonth() + 1;
    const y = now.getFullYear();
    return m === 1 ? { year: y - 1, month: 12 } : { year: y, month: m - 1 };
  }, []);

  const [selectedYear, setSelectedYear] = useState(initialPeriod.year);
  const [selectedMonth, setSelectedMonth] = useState(initialPeriod.month);
  const [statusFilter, setStatusFilter] = useState<NewsletterStatus | "all" | "none">("all");
  const [nameFilter, setNameFilter] = useState("");
  const [showBatchModal, setShowBatchModal] = useState(false);

  const athletesQuery = useAthletes(clubId ? { club_id: clubId } : undefined);
  const athletes = athletesQuery.data?.items ?? [];

  // Resumen de estado de boletines de TODOS los atletas del club en UNA sola
  // petición (reemplaza el fan-out N+1 por card que había antes).
  const summaryQuery = useNewsletterStatusSummary(selectedYear, selectedMonth);
  const newslettersByAthleteId = useMemo(() => {
    const map = new Map<number, NewsletterStatusSummaryItem>();
    for (const item of summaryQuery.data?.items ?? []) {
      map.set(item.athlete_id, item);
    }
    return map;
  }, [summaryQuery.data]);

  const years = Array.from(
    { length: initialPeriod.year - 2023 },
    (_, i) => initialPeriod.year - i,
  );

  // Meses disponibles según año: para el año más reciente, hasta el mes anterior al actual.
  const availableMonths = useMemo(() => {
    const maxMonth =
      selectedYear < initialPeriod.year
        ? 12
        : selectedYear === initialPeriod.year
          ? initialPeriod.month
          : 0;
    return MONTH_NAMES.slice(0, maxMonth).map((name, i) => ({
      value: i + 1,
      name,
    }));
  }, [selectedYear, initialPeriod]);

  // Si el mes seleccionado deja de ser válido al cambiar de año, ajustar al último válido.
  useEffect(() => {
    if (availableMonths.length === 0) return;
    const validValues = availableMonths.map((m) => m.value);
    if (!validValues.includes(selectedMonth)) {
      setSelectedMonth(validValues[validValues.length - 1]);
    }
  }, [availableMonths, selectedMonth]);

  function handleAthleteClick(athleteId: number, newsletterId?: number) {
    if (newsletterId) {
      navigate(
        `/training/athlete-newsletters/${athleteId}/${newsletterId}`,
      );
    } else {
      navigate(`/training/athlete-newsletters/${athleteId}/new`, {
        state: { year: selectedYear, month: selectedMonth },
      });
    }
  }

  return (
    <section className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Boletines Mensuales
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            Boletines individuales por atleta para enviar a sus familias.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowBatchModal(true)}
          disabled={!clubId}
          className="flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-40"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          data-testid="open-batch-modal"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Generar para todos los atletas
        </button>
      </div>

      {/* Filtros */}
      <div
        className="flex flex-wrap gap-3 rounded-xl bg-white p-3"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
      >
        {/* Selector mes */}
        <div className="flex items-center gap-2">
          <label htmlFor="filter-month" className="text-xs font-medium text-mid-gray">
            Mes
          </label>
          <select
            id="filter-month"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(Number(e.target.value))}
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            {availableMonths.map(({ value, name }) => (
              <option key={value} value={value}>
                {name}
              </option>
            ))}
          </select>
        </div>

        {/* Selector año */}
        <div className="flex items-center gap-2">
          <label htmlFor="filter-year" className="text-xs font-medium text-mid-gray">
            Año
          </label>
          <select
            id="filter-year"
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        {/* Filtro por status */}
        <div className="flex items-center gap-2">
          <label htmlFor="filter-status" className="text-xs font-medium text-mid-gray">
            Estado
          </label>
          <select
            id="filter-status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as NewsletterStatus | "all" | "none")}
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            <option value="all">Todos los estados</option>
            <option value="none">Sin generar</option>
            <option value="draft">Borrador</option>
            <option value="approved">Aprobado</option>
            <option value="sent">Enviado</option>
            <option value="failed">Fallido</option>
          </select>
        </div>

        {/* Filtro por nombre */}
        <div className="flex items-center gap-2 flex-1 min-w-[160px]">
          <label htmlFor="filter-name" className="text-xs font-medium text-mid-gray shrink-0">
            Atleta
          </label>
          <input
            id="filter-name"
            type="search"
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
            placeholder="Buscar por nombre..."
            className="w-full rounded-lg px-3 py-1.5 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          />
        </div>
      </div>

      {/* Estados de carga / error */}
      {athletesQuery.isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-xl bg-white"
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            />
          ))}
        </div>
      )}

      {athletesQuery.isError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          No se pudo cargar la lista de atletas.
        </p>
      )}

      {/* Empty state sin atletas */}
      {!athletesQuery.isLoading && !athletesQuery.isError && athletes.length === 0 && (
        <div
          className="rounded-xl bg-white p-10 text-center"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px", borderStyle: "dashed" }}
          data-testid="empty-athletes"
        >
          <FileText className="mx-auto mb-3 h-8 w-8 text-mid-gray" aria-hidden="true" />
          <p className="text-sm font-medium text-charcoal">No hay atletas en el club</p>
          <p className="mt-1 text-xs text-mid-gray">
            Agrega atletas primero para generar boletines.
          </p>
        </div>
      )}

      {/* Grid de atletas */}
      {!athletesQuery.isLoading && !athletesQuery.isError && athletes.length > 0 && (
        <AthleteNewsletterGrid
          athletes={athletes}
          year={selectedYear}
          month={selectedMonth}
          statusFilter={statusFilter}
          nameFilter={nameFilter}
          newslettersByAthleteId={newslettersByAthleteId}
          onAthleteClick={handleAthleteClick}
        />
      )}

      {/* Modal batch */}
      {clubId && (
        <BatchModal
          open={showBatchModal}
          onClose={() => setShowBatchModal(false)}
          year={selectedYear}
          month={selectedMonth}
          clubId={clubId}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Grid component (separated to keep parent clean)
// ---------------------------------------------------------------------------

interface AthleteNewsletterGridProps {
  athletes: AthleteOut[];
  year: number;
  month: number;
  statusFilter: NewsletterStatus | "all" | "none";
  nameFilter: string;
  /** Resumen resuelto en un único useNewsletterStatusSummary del padre. */
  newslettersByAthleteId: Map<number, NewsletterStatusSummaryItem>;
  onAthleteClick: (athleteId: number, newsletterId?: number) => void;
}

function AthleteNewsletterGrid({
  athletes,
  year,
  month,
  statusFilter,
  nameFilter,
  newslettersByAthleteId,
  onAthleteClick,
}: AthleteNewsletterGridProps) {
  return (
    <AthleteGridInner
      athletes={athletes}
      year={year}
      month={month}
      statusFilter={statusFilter}
      nameFilter={nameFilter}
      newslettersByAthleteId={newslettersByAthleteId}
      onAthleteClick={onAthleteClick}
    />
  );
}

/**
 * Inner component that applies the name/status filters. Newsletter status
 * per athlete comes from the single useNewsletterStatusSummary map resolved
 * by the page — cards no longer query their own status independently.
 */
function AthleteGridInner({
  athletes,
  year,
  month,
  statusFilter,
  nameFilter,
  newslettersByAthleteId,
  onAthleteClick,
}: AthleteNewsletterGridProps) {
  // Apply text filter synchronously
  const filteredAthletes = athletes.filter((a) => {
    const fullName = `${a.first_name} ${a.last_name}`.toLowerCase();
    return fullName.includes(nameFilter.toLowerCase());
  });

  if (filteredAthletes.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-mid-gray" data-testid="empty-filtered">
        Ningún atleta coincide con los filtros aplicados.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="athletes-grid">
      {filteredAthletes.map((athlete) => (
        <AthleteCardWithFilter
          key={athlete.id}
          athlete={athlete}
          year={year}
          month={month}
          statusFilter={statusFilter}
          newslettersByAthleteId={newslettersByAthleteId}
          onClick={onAthleteClick}
        />
      ))}
    </div>
  );
}

interface AthleteCardWithFilterProps {
  athlete: AthleteOut;
  year: number;
  month: number;
  statusFilter: NewsletterStatus | "all" | "none";
  newslettersByAthleteId: Map<number, NewsletterStatusSummaryItem>;
  onClick: (athleteId: number, newsletterId?: number) => void;
}

function AthleteCardWithFilter({
  athlete,
  year,
  month,
  statusFilter,
  newslettersByAthleteId,
  onClick,
}: AthleteCardWithFilterProps) {
  const newsletter = newslettersByAthleteId.get(athlete.id);
  const status: NewsletterStatus | "none" = newsletter?.status ?? "none";

  // Apply status filter
  if (statusFilter !== "all") {
    if (statusFilter === "none" && status !== "none") return null;
    if (statusFilter !== "none" && status !== statusFilter) return null;
  }

  return (
    <AthleteNewsletterCard
      athlete={athlete}
      year={year}
      month={month}
      newsletter={newsletter}
      onClick={onClick}
    />
  );
}
