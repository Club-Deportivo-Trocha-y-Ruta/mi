/**
 * HistoricalLoadPage — tablero de carga histórica Copa Valle (feature 044,
 * US5, T064).
 *
 * Ruta: /competitions/history
 * Acceso: coach + admin.
 *
 * Muestra los imports agrupados por temporada, con el estado de cada uno en
 * el mismo camino de confianza que un cargue de temporada vigente
 * (`contracts/historical-load.md`): preview → dry-run → commit, protección
 * de duplicados y candado de identidad. El tablero en sí no repite ese
 * flujo — asume que el archivo ya se subió (Wizard o
 * `scripts/stage_race_history.py`) y ofrece solo las dos acciones que le
 * faltan a una válida ya en `pending`: confirmar el commit, o completar un
 * commit parcial (`commit-pending`).
 *
 * Estados del tablero (`contracts/ui-history.md` §3): categorías por
 * revisar → identidad por revisar → listo → cargado. `season`/`valida_num`/
 * `series_name`/`pending_categories_count` en `ImportListItem` son siempre
 * reales (`contracts/historical-load.md` §"Board fields") — solo `null`
 * para un import roto sin meta ni evento resuelto, tratado aquí como
 * "Sin temporada" en el agrupador.
 *
 * El commit/commit-pending del tablero se dispara con `resolved_matches:
 * []` — la resolución fina de matches de un corredor de club queda en el
 * Import Wizard normal, no en este tablero. Cuando el acta tiene un
 * corredor de club sin resolver, el backend responde `409
 * matches_unresolved` (distinto de `identity_review_pending`, que es el
 * candado de identidad cruzada entre temporadas): el tablero muestra el
 * motivo y enlaza al wizard de esa válida (`/competitions/{event_id}/import`
 * cuando el evento ya existe; `/competitions/import` si no) para que el
 * coach resuelva los matches allí — el wizard no tiene hoy una forma de
 * "reanudar" un import ya staged sin volver a elegir el archivo, así que
 * el enlace lleva al punto de entrada correcto, no a una resolución en un
 * clic.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  FileWarning,
  Loader2,
  UploadCloud,
  UserCheck,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  useCommitPendingRaceImport,
  useImportCommit,
  useImportsHistory,
} from "@/hooks/ai/useRaceImports";
import { useIdentitySummary } from "@/hooks/race/useIdentityReview";
import type { ImportListItem } from "@/types/raceImports.types";

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
  identityPending: number,
): BoardState {
  if (item.status === "committed") return "cargado";
  if (item.status === "failed") return "error_lectura";
  if (item.pending_categories_count > 0) return "categorias_por_revisar";
  if (identityPending > 0) return "identidad_por_revisar";
  return "listo";
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

// ---------------------------------------------------------------------------
// Errores de commit / commit-pending — mismos códigos que el Wizard
// (`ImportWizard.tsx::CommitErrorMessage`), copy y estructura duplicados
// aquí a propósito: son dos superficies independientes y este archivo no
// debía tocar `ImportWizard.tsx` en paralelo con otros agentes.
// ---------------------------------------------------------------------------

interface BoardCommitError {
  message: string;
  /** `"identity"` → link a la revisión de identidad cruzada. `"matches"` →
   * link al Import Wizard de esta válida (matches de club sin resolver). */
  linkTo: "identity" | "matches" | null;
}

function getBoardCommitErrorMessage(err: unknown): BoardCommitError {
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
        pending?: unknown;
        missing_count?: unknown;
      };
      const code = typeof d.code === "string" ? d.code : undefined;
      if (code === "identity_review_pending") {
        const pending = typeof d.pending === "number" ? d.pending : null;
        return {
          message:
            pending != null
              ? `Hay ${pending} posible${pending === 1 ? "" : "s"} coincidencia${
                  pending === 1 ? "" : "s"
                } de identidad por revisar antes de confirmar la carga.`
              : "Hay coincidencias de identidad por revisar antes de confirmar la carga.",
          linkTo: "identity",
        };
      }
      if (code === "nothing_pending") {
        return {
          message: "No hay categorías pendientes por cargar en esta válida.",
          linkTo: null,
        };
      }
      if (code === "matches_unresolved") {
        // El backend siempre manda `message` en español para este código
        // (`contracts/historical-load.md` §"Board fields") — se prioriza
        // sobre un texto genérico armado acá porque ya trae el detalle
        // exacto (cuántos corredores de club quedaron sin resolver).
        const missingCount =
          typeof d.missing_count === "number" ? d.missing_count : null;
        return {
          message:
            typeof d.message === "string"
              ? d.message
              : missingCount != null
                ? `Hay ${missingCount} corredor${missingCount === 1 ? "" : "es"} del club sin coincidencia resuelta.`
                : "Hay corredores del club sin coincidencia resuelta.",
          linkTo: "matches",
        };
      }
      if (typeof d.message === "string") {
        return { message: d.message, linkTo: null };
      }
    }
    if (typeof detail === "string") {
      return { message: detail, linkTo: null };
    }
    if (e.response?.status === 503) {
      return {
        message:
          "El recálculo de identidad tardó demasiado. Intenta de nuevo en unos minutos.",
        linkTo: null,
      };
    }
  }
  return {
    message: "No se pudo completar la acción. Intenta de nuevo.",
    linkTo: null,
  };
}

// ---------------------------------------------------------------------------
// Banner de identidad
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
            Hay {pending} posible{pending === 1 ? "" : "s"} coincidencia
            {pending === 1 ? "" : "s"} de identidad por revisar. El commit de
            cualquier válida histórica queda bloqueado hasta resolverlas.
          </span>
        </div>
        <Link
          to="/competitions/identity-review"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Revisar identidad
        </Link>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Fila de un import dentro de un grupo de temporada
// ---------------------------------------------------------------------------

interface ImportRowProps {
  item: ImportListItem;
  boardState: BoardState;
}

function ImportRow({ item, boardState }: ImportRowProps) {
  const [actionError, setActionError] = useState<BoardCommitError | null>(
    null,
  );
  const commitMutation = useImportCommit();
  const commitPendingMutation = useCommitPendingRaceImport();

  const isBusy = commitMutation.isPending || commitPendingMutation.isPending;

  function handleCommit() {
    setActionError(null);
    commitMutation.mutate(
      { parseId: item.id, body: { resolved_matches: [] } },
      {
        onSuccess: (data) => {
          toast.success(
            `Válida cargada: ${data.n_results_inserted} resultado(s).`,
          );
        },
        onError: (err) => setActionError(getBoardCommitErrorMessage(err)),
      },
    );
  }

  function handleCommitPending() {
    setActionError(null);
    commitPendingMutation.mutate(
      { parseId: item.id },
      {
        onSuccess: (data) => {
          toast.success(
            `Categorías pendientes cargadas: ${data.n_results_inserted} resultado(s).`,
          );
        },
        onError: (err) => setActionError(getBoardCommitErrorMessage(err)),
      },
    );
  }

  const canCommit = boardState === "listo";
  const canCommitPending =
    item.status !== "committed" &&
    item.pending_categories_count > 0 &&
    boardState !== "identidad_por_revisar";
  const wizardHref = item.event_id
    ? `/competitions/${item.event_id}/import`
    : "/competitions/import";

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
              {actionError.linkTo === "identity" && (
                <Link
                  to="/competitions/identity-review"
                  className="font-medium underline underline-offset-2"
                >
                  Ir a la revisión de identidad
                </Link>
              )}
              {actionError.linkTo === "matches" && (
                <Link
                  to={wizardHref}
                  className="font-medium underline underline-offset-2"
                  data-testid={`import-row-wizard-link-${item.id}`}
                >
                  Ir al asistente de importación
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
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function HistoricalLoadPage() {
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
    <section className="mx-auto max-w-4xl space-y-5 px-4 py-6">
      <PageHeader
        title="Carga histórica"
        subtitle="Válidas de temporadas pasadas cargadas por el mismo camino de confianza que la temporada vigente."
        backTo={{ to: "/competitions", label: "Volver a competencias" }}
        actions={
          <Link
            to="/competitions/import"
            className={buttonVariants({ variant: "outline" })}
          >
            <UploadCloud size={14} aria-hidden="true" className="mr-1.5" />
            Cargar archivo
          </Link>
        }
      />

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
                  <ImportRow
                    key={item.id}
                    item={item}
                    boardState={computeBoardState(item, identityPending)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && !isError && identityPending === 0 && items.length > 0 && (
        <p className="flex items-center gap-1.5 text-xs text-mid-gray">
          <CheckCircle2 size={12} aria-hidden="true" />
          Identidad al día — ninguna carga histórica está bloqueada por
          revisión pendiente.
        </p>
      )}
    </section>
  );
}

export default HistoricalLoadPage;
