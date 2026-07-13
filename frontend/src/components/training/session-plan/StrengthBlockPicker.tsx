/**
 * StrengthBlockPicker — biblioteca de bloques de fuerza ya guardados por el
 * club, con adjunto directo a una sesión de entrenamiento (feature 032, US1,
 * T016, research.md R7). Mirror de `TemplatePicker.tsx` (intervalos): lista
 * de tarjetas con un botón "Adjuntar a la sesión" por tarjeta y estados
 * idle/pending/success/error idénticos a ese componente de referencia.
 *
 * A diferencia de intervalos y de `BlockAssembler.tsx`, adjuntar un bloque
 * existente a una sesión no tiene compuerta por edad: `AgeBandGuardrailDialog`
 * solo se dispara al crear/editar un bloque (`services/strength/blocks.py`
 * `_validate_age_band_guardrail`), nunca en `POST /blocks/{id}/attach`
 * (research.md R9). Un `409` aquí significa que el par
 * `(training_session_id, block_id)` ya existe — se muestra como un aviso
 * suave ("ya está adjunto"), nunca como un error bloqueante
 * (contracts/unified-attach-flow.md, tabla de estados).
 */
import * as React from "react";
import { Check, Info, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { isAlreadyAttachedError, mapStrengthError } from "@/api/strength";
import { STRENGTH_AGE_BAND_LABEL } from "@/components/strength/ExerciseCard";
import { useAttachBlock, useStrengthBlocks } from "@/hooks/strength/useStrength";
import { cn } from "@/lib/utils";
import type {
  StrengthAttachOut,
  StrengthBlockOut,
} from "@/schemas/strength.schemas";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface StrengthBlockPickerProps {
  /** Sesión de entrenamiento ya existente a la que se adjuntan los bloques. */
  trainingSessionId: number;
  /** Llamado con el adjunto recién creado tras un éxito real (no un 409). */
  onAttached?: (attach: StrengthAttachOut) => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// Estado por tarjeta tras intentar adjuntar
// ---------------------------------------------------------------------------

type BlockAttachStatus = "idle" | "attached" | "already-attached";

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function StrengthBlockPicker({
  trainingSessionId,
  onAttached,
  className,
}: StrengthBlockPickerProps): React.ReactElement {
  const { data, isLoading, isError, error, refetch } = useStrengthBlocks();
  const attach = useAttachBlock();

  const [statusByBlock, setStatusByBlock] = React.useState<
    Record<number, BlockAttachStatus>
  >({});
  const [errorByBlock, setErrorByBlock] = React.useState<
    Record<number, string>
  >({});

  const attachingBlockId =
    attach.isPending && attach.variables ? attach.variables.blockId : null;

  function handleAttach(block: StrengthBlockOut) {
    setErrorByBlock((prev) => {
      if (!(block.id in prev)) return prev;
      const next = { ...prev };
      delete next[block.id];
      return next;
    });
    attach.mutate(
      { blockId: block.id, trainingSessionId },
      {
        onSuccess: (result) => {
          setStatusByBlock((prev) => ({ ...prev, [block.id]: "attached" }));
          toast.success(`"${block.name}" adjuntado a la sesión.`);
          onAttached?.(result);
        },
        onError: (err) => {
          if (isAlreadyAttachedError(err)) {
            // 409 — aviso suave inline, no un error: sin toast (evita ruido
            // duplicado sobre un resultado que, desde el punto de vista del
            // coach, ya estaba logrado — contracts/unified-attach-flow.md).
            setStatusByBlock((prev) => ({
              ...prev,
              [block.id]: "already-attached",
            }));
            return;
          }
          const message = mapStrengthError(err).message;
          setErrorByBlock((prev) => ({
            ...prev,
            [block.id]: message,
          }));
          toast.error(message);
        },
      },
    );
  }

  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando bloques de fuerza del club…"
        className={cn("grid gap-4 sm:grid-cols-2", className)}
      >
        {Array.from({ length: 4 }).map((_, i) => (
          <BlockCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className={cn(
          "rounded-xl border border-red-200 bg-red-50 p-6 text-center",
          className,
        )}
      >
        <p className="text-sm font-medium text-red-800">
          {mapStrengthError(error).message}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => void refetch()}
          className="mt-3 min-h-10"
        >
          Reintentar
        </Button>
      </div>
    );
  }

  const items = data?.items ?? [];

  if (items.length === 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-slate-200 bg-white p-8 text-center",
          className,
        )}
      >
        <p className="text-sm font-medium text-slate-700">
          Aún no hay bloques de fuerza guardados en el club
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Arma uno nuevo desde &ldquo;Armar bloque de fuerza&rdquo; y volvé
          para adjuntarlo.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn("grid gap-4 sm:grid-cols-2", className)}
      aria-label={`Bloques de fuerza del club: ${items.length}`}
    >
      {items.map((block) => (
        <BlockCard
          key={block.id}
          block={block}
          status={statusByBlock[block.id] ?? "idle"}
          isAttaching={attachingBlockId === block.id}
          attachDisabled={
            attachingBlockId != null && attachingBlockId !== block.id
          }
          errorMessage={errorByBlock[block.id] ?? null}
          onAttach={() => handleAttach(block)}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton de carga
// ---------------------------------------------------------------------------

function BlockCardSkeleton(): React.ReactElement {
  return (
    <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-card">
      <Skeleton className="mb-2 h-4 w-3/4" />
      <div className="mb-3 flex gap-1.5">
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-5 w-14 rounded-full" />
      </div>
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tarjeta de bloque
// ---------------------------------------------------------------------------

interface BlockCardProps {
  block: StrengthBlockOut;
  status: BlockAttachStatus;
  isAttaching: boolean;
  attachDisabled: boolean;
  errorMessage: string | null;
  onAttach: () => void;
}

function BlockCard({
  block,
  status,
  isAttaching,
  attachDisabled,
  errorMessage,
  onAttach,
}: BlockCardProps): React.ReactElement {
  const entryCount = block.entries.length;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{block.name}</CardTitle>
          {block.is_archived && (
            <Badge variant="outline" className="shrink-0 text-xs">
              Archivado
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-3 pb-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary" className="text-xs">
            {STRENGTH_AGE_BAND_LABEL[block.target_age_band]} años
          </Badge>
        </div>
        <p className="text-xs text-slate-500">
          {entryCount} {entryCount === 1 ? "ejercicio" : "ejercicios"} ·{" "}
          {block.total_duration_min} min
        </p>

        {errorMessage ? (
          <p
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700"
          >
            {errorMessage}
          </p>
        ) : null}
      </CardContent>

      <CardFooter className="pt-0">
        {status === "attached" ? (
          <p className="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800">
            <Check className="h-4 w-4" aria-hidden="true" />
            Adjuntado a la sesión
          </p>
        ) : status === "already-attached" ? (
          <p className="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-600">
            <Info className="h-4 w-4" aria-hidden="true" />
            Ya está adjunto a esta sesión
          </p>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={onAttach}
            disabled={isAttaching || attachDisabled}
            className="w-full"
          >
            {isAttaching ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Plus className="h-4 w-4" aria-hidden="true" />
            )}
            {isAttaching ? "Adjuntando…" : "Adjuntar a la sesión"}
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

export default StrengthBlockPicker;
