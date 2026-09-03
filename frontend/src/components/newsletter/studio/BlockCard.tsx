/**
 * BlockCard — una tarjeta por bloque narrativo de la bitácora, feature 038
 * (T302, contracts/api.md, plan.md "Coach studio").
 *
 * Chrome genérico (estado, contador de palabras, edición inline, Regenerar,
 * Ocultar) sobre un valor de texto plano — la conversión hacia/desde la
 * forma estructurada de cada bloque (`observations`, `analyst_reading`,
 * `family_compass`) vive en `blockSerializers.ts`, fuera de este componente.
 *
 * Constitution III: el estado nunca se comunica solo con color — StatusBadge
 * ya combina ícono + texto (src/components/shared/StatusBadge.tsx).
 */
import { useEffect, useState } from "react";
import { AlertCircle, Eye, EyeOff, FileText, Pencil, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { BlockState } from "@/types/stageLog.types";
import { countWords } from "@/components/newsletter/studio/blockSerializers";

const BLOCK_STATE_META: Record<
  BlockState,
  { label: string; status: Status; icon: LucideIcon }
> = {
  ai: { label: "IA", status: "neutral", icon: Sparkles },
  edited: { label: "Editado", status: "warning", icon: Pencil },
  static: { label: "Estático", status: "neutral", icon: FileText },
  hidden: { label: "Oculto", status: "neutral", icon: EyeOff },
  empty: { label: "Vacío", status: "danger", icon: AlertCircle },
};

export interface BlockCardProps {
  /** Nombre del bloque para anclar el scroll del preview (`data-block`). */
  dataBlock: string;
  title: string;
  state: BlockState;
  /** Texto plano actual del bloque (ya serializado si el bloque es compuesto). */
  value: string;
  /** Si es `false`, la tarjeta solo muestra estado + Ocultar (fotos, insignias). */
  editable?: boolean;
  /** Si es `false`, no se ofrece "Regenerar" (nota del entrenador, fotos, insignias). */
  regenerable?: boolean;
  hideable?: boolean;
  hidden?: boolean;
  isSaving?: boolean;
  maxWords?: number;
  onSave?: (value: string) => void;
  onRegenerateClick?: () => void;
  onHideToggle?: () => void;
  /** Click en la tarjeta (fuera de los controles) — hace scroll al preview. */
  onCardClick?: () => void;
}

export function BlockCard({
  dataBlock,
  title,
  state,
  value,
  editable = true,
  regenerable = true,
  hideable = false,
  hidden = false,
  isSaving = false,
  maxWords,
  onSave,
  onRegenerateClick,
  onHideToggle,
  onCardClick,
}: BlockCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  // Si el valor canónico cambia (respuesta del PATCH/regenerate), el draft
  // local se sincroniza — evita mostrar texto obsoleto tras guardar.
  useEffect(() => {
    if (!isEditing) setDraft(value);
  }, [value, isEditing]);

  const meta = BLOCK_STATE_META[state];
  const wordCount = countWords(isEditing ? draft : value);
  const overLimit = maxWords != null && wordCount > maxWords;

  function handleSave() {
    onSave?.(draft);
    setIsEditing(false);
  }

  function handleCancel() {
    setDraft(value);
    setIsEditing(false);
  }

  return (
    <div
      className="rounded-xl bg-white px-4 py-3 shadow-card"
      data-testid={`block-card-${dataBlock}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-charcoal">
          {onCardClick ? (
            <button
              type="button"
              onClick={onCardClick}
              className="text-left underline-offset-2 transition-opacity hover:opacity-70 hover:underline"
              data-testid={`block-title-${dataBlock}`}
              aria-label={`${title} — ver en el preview`}
            >
              {title}
            </button>
          ) : (
            title
          )}
        </h3>
        <div className="flex items-center gap-2">
          <StatusBadge status={meta.status} label={meta.label} icon={meta.icon} />
          {editable && (
            <span
              className={cn("text-xs", overLimit ? "text-danger" : "text-mid-gray")}
              data-testid={`block-word-count-${dataBlock}`}
            >
              {wordCount} {wordCount === 1 ? "palabra" : "palabras"}
            </span>
          )}
        </div>
      </div>

      {editable && isEditing ? (
        <div className="mt-2 space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={isSaving}
            aria-label={`Editar ${title}`}
            rows={4}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="rounded-lg bg-charcoal px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              data-testid={`block-save-${dataBlock}`}
            >
              Guardar
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={isSaving}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70 disabled:opacity-50"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-2 whitespace-pre-line text-sm text-charcoal">
          {value || <span className="text-mid-gray italic">Sin contenido.</span>}
        </p>
      )}

      {!isEditing && (
        <div className="mt-3 flex flex-wrap gap-3 text-xs font-medium text-charcoal">
          {editable && (
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center gap-1 transition-opacity hover:opacity-70"
              data-testid={`block-edit-${dataBlock}`}
              aria-label={`Editar ${title}`}
            >
              <Pencil size={12} aria-hidden="true" /> Editar
            </button>
          )}
          {regenerable && onRegenerateClick && (
            <button
              type="button"
              onClick={onRegenerateClick}
              className="inline-flex items-center gap-1 transition-opacity hover:opacity-70"
              data-testid={`block-regenerate-${dataBlock}`}
              aria-label={`Regenerar ${title}`}
            >
              <Sparkles size={12} aria-hidden="true" /> Regenerar
            </button>
          )}
          {hideable && onHideToggle && (
            <button
              type="button"
              onClick={onHideToggle}
              className="inline-flex items-center gap-1 transition-opacity hover:opacity-70"
              data-testid={`block-hide-toggle-${dataBlock}`}
              aria-label={hidden ? `Mostrar ${title}` : `Ocultar ${title}`}
            >
              {hidden ? (
                <>
                  <Eye size={12} aria-hidden="true" /> Mostrar
                </>
              ) : (
                <>
                  <EyeOff size={12} aria-hidden="true" /> Ocultar
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
