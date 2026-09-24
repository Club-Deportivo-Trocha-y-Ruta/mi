/**
 * LoadsSection — «Cargas»: tablero de cargas de «Cargas e identidades»
 * (feature 045, US3; nace del cuerpo de `HistoricalLoadPage`, feature 044 US5).
 *
 * Muestra los imports agrupados por temporada, con el estado de cada uno en
 * el mismo camino de confianza que un cargue de temporada vigente
 * (`contracts/historical-load.md`): preview → dry-run → commit, protección de
 * duplicados y candado de identidad. Ofrece, para una carga ya en `pending`:
 * confirmar el commit, completar un commit parcial (`commit-pending`), retomar
 * el asistente donde se dejó (`/competitions/import?import=<id>`) o descartarla.
 *
 * Candado de identidad POR CARGA (feature 045, R-08): el tablero ya no marca
 * todas las cargas como «Identidad por revisar» cuando la cola tiene
 * candidatos — solo bloquea el servidor (`409 identity_pending`) las cargas
 * que los involucran. Aquí ese estado aparece en la fila que recibió el 409.
 *
 * Estados del tablero (`contracts/ui-history.md` §3): categorías por revisar →
 * (identidad por revisar, tras un 409) → listo → cargado. `season`/`valida_num`/
 * `series_name`/`pending_categories_count` en `ImportListItem` son siempre
 * reales (`contracts/historical-load.md` §"Board fields") — solo `null` para un
 * import roto sin meta ni evento resuelto, tratado como "Sin temporada".
 *
 * El commit/commit-pending del tablero se dispara con `resolved_matches: []`
 * — la resolución fina de matches de un corredor de club queda en el asistente.
 * Cuando el acta tiene un corredor de club sin resolver, el backend responde
 * `409 matches_unresolved`: la fila muestra el motivo y enlaza a RETOMAR la
 * carga en el asistente (que ahora sí conserva el archivo ya subido).
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  FileWarning,
  Loader2,
  PlayCircle,
  Trash2,
  UploadCloud,
  UserCheck,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { DiscardImportDialog } from "@/components/competitions/imports/DiscardImportDialog";
import {
  useCommitPendingRaceImport,
  useImportCommit,
  useImportsHistory,
} from "@/hooks/ai/useRaceImports";
import { useIdentitySummary } from "@/hooks/race/useIdentityReview";
import { getIdentityPendingInfo, identityGateMessage } from "@/lib/identityGate";
import type { ImportListItem } from "@/types/raceImports.types";

/** Sección de identidades dentro de «Cargas e identidades». */
const IDENTITY_SECTION_PATH = "/competitions/imports?seccion=identidades";

// ---------------------------------------------------------------------------
// Estado del tablero — derivado por item (contracts/ui-history.md §3)
// ---------------------------------------------------------------------------

type BoardState =
  | "categorias_por_revisar"
  | "identidad_por_revisar"
  | "listo"
  | "cargado"
  | "error_lectura";

const BOARD_STATE_LABELS: Record<BoardState, string> = {
  categorias_por_revisar: "Categorías por revisar",
  identidad_por_revisar: "Identidad por revisar",
  listo: "Listo para cargar",
  cargado: "Cargado",
  error_lectura: "No se pudo leer",
};

const BOARD_STATE_BADGE_VARIANT: Record<
  BoardState,
  "secondary" | "warning" | "info" | "success" | "destructive"
> = {
  categorias_por_revisar: "warning",
  identidad_por_revisar: "warning",
  listo: "info",
  cargado: "success",
  error_lectura: "destructive",
};

function computeBoardState(
  item: ImportListItem,
  identityBlocked: boolean,
): BoardState {
  if (item.status === "committed") return "cargado";
  if (item.status === "failed") return "error_lectura";
  if (item.pending_categories_count > 0) return "categorias_por_revisar";
  if (identityBlocked) return "identidad_por_revisar";
  return "listo";
}

/** Una carga «en curso» se puede retomar y descartar (pending | dry_run). */
function isInProgress(item: ImportListItem): boolean {
  return item.status === "pending" || item.status === "dry_run";
}

const SEASON_FALLBACK_KEY = "sin-temporada";

function seasonKey(item: ImportListItem): string {
  return item.season != null ? String(item.season) : SEASON_FALLBACK_KEY;
}

function seasonLabel(key: string): string {
  return key === SEASON_FALLBACK_KEY ? "Sin temporada" : `Temporada ${key}`;
}

function importLabel(item: ImportListItem): string {
  const parts: string[] = [];
  if (item.series_name) parts.push(item.series_name);
  if (item.valida_num != null) parts.push(`Válida ${item.valida_num}`);
  if (parts.length === 0) return item.original_filename;
  return parts.join(" · ");
}

/** Ruta del asistente que RETOMA esta carga sin volver a subir el archivo. */
function resumeHref(item: ImportListItem): string {
  return `/competitions/import?import=${item.id}`;
}

// ---------------------------------------------------------------------------
// Errores de commit / commit-pending
// ---------------------------------------------------------------------------

interface BoardCommitError {
  message: string;
  /** `"identity"` → link a las decisiones de esta carga (`review_path`).
   * `"matches"` → link para retomar la carga en el asistente. */
  link: { kind: "identity"; to: string } | { kind: "matches" } | null;
}

function getBoardCommitError(err: unknown): BoardCommitError {
  const identity = getIdentityPendingInfo(err);
  if (identity) {
    return {
      message: identityGateMessage(identity.pending),
      link: { kind: "identity", to: identity.reviewPath },
    };
  }

  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const detail = e.response?.data?.detail;
    if (
      detail &&
      typeof detail === "object" &&
      !Array.isArray(detail) &&
      "code" in detail
    ) {
      const d = detail as {
        code?: unknown;
        message?: unknown;
        missing_count?: unknown;
      };
      const code = typeof d.code === "string" ? d.code : undefined;
      if (code === "nothing_pending") {
        return {
          message: "No hay categorías pendientes por cargar en esta válida.",
          link: null,
        };
      }
      if (code === "matches_unresolved") {
        // El backend siempre manda `message` en español para este código
        // (`contracts/historical-load.md` §"Board fields") — se prioriza
        // porque ya trae el detalle exacto (cuántos corredores del club
        // quedaron sin resolver).
        const missingCount =
          typeof d.missing_count === "number" ? d.missing_count : null;
        return {
          message:
            typeof d.message === "string"
              ? d.message
              : missingCount != null
                ? `Hay ${missingCount} corredor${missingCount === 1 ? "" : "es"} del club sin coincidencia resuelta.`
                : "Hay corredores del club sin coincidencia resuelta.",
          link: { kind: "matches" },
        };
      }
      if (typeof d.message === "string") {
        return { message: d.message, link: null };
      }
    }
    if (typeof detail === "string") {
      return { message: detail, link: null };
    }
    if (e.response?.status === 503) {
      return {
        message:
          "El recálculo de identidad tardó demasiado. Intenta de nuevo en unos minutos.",
        link: null,
      };
    }
  }
  return {
    message: "No se pudo completar la acción. Intenta de nuevo.",
    link: null,
  };
}

// ---------------------------------------------------------------------------
// Banner de identidad (informativo — ya no bloquea todas las cargas)
// ---------------------------------------------------------------------------

function IdentityBanner({ pending }: { pending: number }) {
  if (pending <= 0) return null;
  return (
    <Card
      className="border border-amber-200 bg-amber-50"
      data-testid="identity-banner"
    >
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-2 text-sm text-amber-900">
          <UserCheck size={16} aria-hidden="true" />
          <span>
            {pending === 1
              ? "Hay 1 decisión de identidad por tomar. Solo bloquea"
              : `Hay ${pending} decisiones de identidad por tomar. Solo bloquean`}{" "}
            la carga de las competencias que {pending === 1 ? "la" : "las"}{" "}
            involucran.
          </span>
        </div>
        <Link
          to={IDENTITY_SECTION_PATH}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Ver decisiones
        </Link>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Fila de un import dentro de un grupo de temporada
// ---------------------------------------------------------------------------

function ImportRow({ item }: { item: ImportListItem }) {
  const [actionError, setActionError] = useState<BoardCommitError | null>(null);
  const [identityBlocked, setIdentityBlocked] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const commitMutation = useImportCommit();
  const commitPendingMutation = useCommitPendingRaceImport();

  const isBusy = commitMutation.isPending || commitPendingMutation.isPending;
  const boardState = computeBoardState(item, identityBlocked);

  function handleError(err: unknown) {
    const parsed = getBoardCommitError(err);
    setIdentityBlocked(parsed.link?.kind === "identity");
    setActionError(parsed);
  }

  function handleCommit() {
    setActionError(null);
    setIdentityBlocked(false);
    commitMutation.mutate(
      { parseId: item.id, body: { resolved_matches: [] } },
      {
        onSuccess: (data) => {
          toast.success(
            `Válida cargada: ${data.n_results_inserted} resultado(s).`,
          );
        },
        onError: handleError,
      },
    );
  }

  function handleCommitPending() {
    setActionError(null);
    setIdentityBlocked(false);
    commitPendingMutation.mutate(
      { parseId: item.id },
      {
        onSuccess: (data) => {
          toast.success(
            `Categorías pendientes cargadas: ${data.n_results_inserted} resultado(s).`,
          );
        },
        onError: handleError,
      },
    );
  }

  const inProgress = isInProgress(item);
  const canCommit = boardState === "listo" || boardState === "identidad_por_revisar";
  const canCommitPending =
    item.status !== "committed" &&
    item.pending_categories_count > 0 &&
    boardState !== "identidad_por_revisar";

  return (
    <Card data-testid={`import-row-${item.id}`}>
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-medium text-charcoal">
            {importLabel(item)}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={BOARD_STATE_BADGE_VARIANT[boardState]}>
              {BOARD_STATE_LABELS[boardState]}
            </Badge>
            {item.pending_categories_count > 0 && (
              <Badge variant="outline" data-testid={`pending-categories-${item.id}`}>
                {item.pending_categories_count} categoría
                {item.pending_categories_count === 1 ? "" : "s"} pendiente
                {item.pending_categories_count === 1 ? "" : "s"}
              </Badge>
            )}
            <span className="text-xs text-mid-gray">
              {item.n_results} resultado{item.n_results === 1 ? "" : "s"}
            </span>
          </div>
          {actionError && (
            <p
              className="text-xs text-red-700"
              role="alert"
              data-testid={`import-row-error-${item.id}`}
            >
              {actionError.message}{" "}
              {actionError.link?.kind === "identity" && (
                <Link
                  to={actionError.link.to}
                  className="font-medium underline underline-offset-2"
                  data-testid={`import-row-identity-link-${item.id}`}
                >
                  Ir a las decisiones de identidad
                </Link>
              )}
              {actionError.link?.kind === "matches" && (
                <Link
                  to={resumeHref(item)}
                  className="font-medium underline underline-offset-2"
                  data-testid={`import-row-wizard-link-${item.id}`}
                >
                  Retomar en el asistente de importación
                </Link>
              )}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          {canCommit && (
            <Button
              type="button"
              size="sm"
              className="min-h-12"
              disabled={isBusy}
              onClick={handleCommit}
              data-testid={`commit-${item.id}`}
            >
              {commitMutation.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  Cargando...
                </>
              ) : (
                "Confirmar carga"
              )}
            </Button>
          )}
          {canCommitPending && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="min-h-12"
              disabled={isBusy}
              onClick={handleCommitPending}
              data-testid={`commit-pending-${item.id}`}
            >
              {commitPendingMutation.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  Completando...
                </>
              ) : (
                "Completar pendientes"
              )}
            </Button>
          )}
          {inProgress && (
            <Link
              to={resumeHref(item)}
              className={buttonVariants({
                variant: "outline",
                size: "sm",
                className: "min-h-12",
              })}
              data-testid={`resume-${item.id}`}
            >
              <PlayCircle size={14} aria-hidden="true" className="mr-1.5" />
              Retomar
            </Link>
          )}
          {inProgress && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="min-h-12 text-red-700 hover:text-red-800"
              disabled={isBusy}
              onClick={() => setDiscardOpen(true)}
              data-testid={`discard-${item.id}`}
            >
              <Trash2 size={14} aria-hidden="true" className="mr-1.5" />
              Descartar
            </Button>
          )}
        </div>
      </CardContent>

      {inProgress && (
        <DiscardImportDialog
          open={discardOpen}
          onOpenChange={setDiscardOpen}
          importId={item.id}
          filename={item.original_filename}
        />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sección
// ---------------------------------------------------------------------------

export function LoadsSection() {
  const historyQuery = useImportsHistory({ limit: 100 });
  const identitySummaryQuery = useIdentitySummary();

  const identityPending = identitySummaryQuery.data?.pending ?? 0;
  const items = historyQuery.data?.items ?? [];

  const groups = useMemo(() => {
    const byKey = new Map<string, ImportListItem[]>();
    for (const item of items) {
      const key = seasonKey(item);
      const list = byKey.get(key) ?? [];
      list.push(item);
      byKey.set(key, list);
    }
    return Array.from(byKey.entries())
      .sort(([a], [b]) => {
        if (a === SEASON_FALLBACK_KEY) return 1;
        if (b === SEASON_FALLBACK_KEY) return -1;
        return Number(b) - Number(a);
      })
      .map(([key, groupItems]) => ({
        key,
        label: seasonLabel(key),
        items: [...groupItems].sort((a, b) => {
          const av = a.valida_num ?? Number.MAX_SAFE_INTEGER;
          const bv = b.valida_num ?? Number.MAX_SAFE_INTEGER;
          return av - bv;
        }),
      }));
  }, [items]);

  const isLoading = historyQuery.isLoading;
  const isError = historyQuery.isError;

  return (
    <div className="space-y-5" data-testid="loads-section">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-mid-gray">
          Competencias cargadas por el mismo camino de confianza que la
          temporada vigente. Retoma una carga en curso donde la dejaste, sin
          volver a subir el archivo.
        </p>
        <Link
          to="/competitions/import"
          className={buttonVariants({ variant: "outline", className: "min-h-12" })}
        >
          <UploadCloud size={14} aria-hidden="true" className="mr-1.5" />
          Cargar archivo
        </Link>
      </div>

      <IdentityBanner pending={identityPending} />

      {isLoading && (
        <div
          className="flex min-h-[30vh] items-center justify-center gap-2 text-sm text-mid-gray"
          role="status"
          aria-live="polite"
        >
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          Cargando cargues históricos...
        </div>
      )}

      {isError && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <AlertCircle size={24} className="text-red-600" aria-hidden="true" />
            <p className="text-sm text-charcoal">
              No se pudo cargar el tablero de cargas históricas.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-12"
              onClick={() => historyQuery.refetch()}
            >
              Reintentar
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={FileWarning}
          title="Todavía no hay cargues históricos"
          description="Sube el primer archivo de una válida pasada desde el asistente de importación."
          action={
            <Link to="/competitions/import" className={buttonVariants()}>
              Cargar archivo
            </Link>
          }
        />
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="space-y-6">
          {groups.map((group) => (
            <div key={group.key} className="space-y-3">
              <h2 className="font-display text-lg text-charcoal">
                {group.label}
              </h2>
              <div className="space-y-2">
                {group.items.map((item) => (
                  <ImportRow key={item.id} item={item} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && !isError && identityPending === 0 && items.length > 0 && (
        <p className="flex items-center gap-1.5 text-xs text-mid-gray">
          <CheckCircle2 size={12} aria-hidden="true" />
          Identidad al día — ninguna carga está bloqueada por decisiones
          pendientes.
        </p>
      )}
    </div>
  );
}
