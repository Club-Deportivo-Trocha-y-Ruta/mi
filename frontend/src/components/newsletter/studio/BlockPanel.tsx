/**
 * BlockPanel — panel derecho del estudio: una `BlockCard` por bloque
 * narrativo + los bloques opcionales no-narrativos (fotos, insignias, nota
 * del entrenador), feature 038 (T302).
 *
 * Mapea cada bloque de `StageLog` a texto plano vía `blockSerializers` para
 * `BlockCard`, y de vuelta a la forma estructurada de `StageOverrides` al
 * guardar. El anclaje de scroll (`data-block`) usa los nombres reales que
 * `StageLogView` (T301) pone en cada bloque raíz: `header`, `trail`,
 * `summit`, `observations`, `analyst-reading`, `effort-profile`,
 * `next-segment`, `family-compass`, `badges`, `photos`, `coach-note`
 * (kebab-case — ver `components/newsletter/StageLogView.tsx`).
 *
 * Feature 045 (T063): sobre la «Nota del entrenador» se ofrece «Insertar aviso
 * de cambios» (ver `changeNotice.ts`). Un clic abre el editor de esa nota con
 * el aviso ya escrito; el coach lo edita y lo guarda — nada se persiste ni se
 * envía hasta que pulsa «Guardar». La oferta sólo aparece mientras la nota
 * está vacía (no pisa lo que el coach escribió) y hasta que el coach la
 * descarta (se recuerda por coach en localStorage).
 */
import { useState } from "react";
import { Megaphone } from "lucide-react";

import { BlockCard } from "@/components/newsletter/studio/BlockCard";
import {
  parseAnalystReading,
  parseFamilyCompass,
  parseObservations,
  serializeAnalystReading,
  serializeFamilyCompass,
  serializeObservations,
} from "@/components/newsletter/studio/blockSerializers";
import {
  CHANGE_NOTICE_TEXT,
  useChangeNoticeOffer,
} from "@/components/newsletter/studio/changeNotice";
import { useAuthStore } from "@/store/auth.store";
import type {
  HideableBlock,
  RegenerableBlock,
  StageLog,
  StageOverrides,
} from "@/types/stageLog.types";

/** `data-block` del preview correspondiente a cada bloque editable/ocultable. */
export const BLOCK_DATA_ANCHORS: Record<string, string> = {
  stage_title: "header",
  summit_caption: "summit",
  observations: "observations",
  analyst_reading: "analyst-reading",
  next_segment_text: "next-segment",
  family_compass: "family-compass",
  coach_note: "coach-note",
  photos: "photos",
  badges: "badges",
};

const MAX_WORDS: Partial<Record<RegenerableBlock | "coach_note", number>> = {
  stage_title: 20,
  summit_caption: 25,
  next_segment_text: 40,
  family_compass: 90,
  analyst_reading: 45,
  coach_note: 60,
};

export interface BlockPanelProps {
  /** StageLog canónico (server) fusionado con el draft local de overrides — igual al del preview. */
  stageLog: StageLog;
  hiddenBlocks: HideableBlock[];
  isSaving?: boolean;
  regeneratingBlock?: RegenerableBlock | null;
  onSaveBlock: (block: RegenerableBlock, overridePatch: Partial<StageOverrides>) => void;
  onSaveCoachNote: (note: string) => void;
  onRegenerateClick: (block: RegenerableBlock) => void;
  onHideToggle: (block: HideableBlock) => void;
  onScrollToBlock: (dataBlock: string) => void;
}

export function BlockPanel({
  stageLog,
  hiddenBlocks,
  isSaving = false,
  regeneratingBlock = null,
  onSaveBlock,
  onSaveCoachNote,
  onRegenerateClick,
  onHideToggle,
  onScrollToBlock,
}: BlockPanelProps) {
  const isHidden = (block: HideableBlock) => hiddenBlocks.includes(block);

  // Oferta «Insertar aviso de cambios» (feature 045, T063).
  const userId = useAuthStore((s) => s.user?.id);
  const { canOffer, dismissed, dismiss } = useChangeNoticeOffer(userId);
  // Cada clic vuelve a sembrar el editor: la tarjeta se remonta con otra `key`.
  const [noticeSeed, setNoticeSeed] = useState(0);
  const noteIsEmpty = !stageLog.coach_note?.trim();
  const showNoticeOffer =
    canOffer && !dismissed && noteIsEmpty && !isHidden("coach_note");

  return (
    <div className="space-y-3" data-testid="block-panel">
      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.stage_title}
        title="Título de la etapa"
        state={stageLog.block_states.stage_title ?? "empty"}
        value={stageLog.stage_title ?? ""}
        maxWords={MAX_WORDS.stage_title}
        isSaving={isSaving && regeneratingBlock === null}
        onSave={(value) => onSaveBlock("stage_title", { stage_title: value })}
        onRegenerateClick={() => onRegenerateClick("stage_title")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.stage_title)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.summit_caption}
        title="Cima del mes"
        state={stageLog.block_states.summit_caption ?? "empty"}
        value={stageLog.summit?.caption ?? ""}
        editable={!!stageLog.summit}
        regenerable={!!stageLog.summit}
        maxWords={MAX_WORDS.summit_caption}
        isSaving={isSaving}
        onSave={(value) => onSaveBlock("summit_caption", { summit_caption: value })}
        onRegenerateClick={() => onRegenerateClick("summit_caption")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.summit_caption)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.observations}
        title="Lo que vio el entrenador"
        state={stageLog.block_states.observations ?? "empty"}
        value={serializeObservations(stageLog.observations)}
        isSaving={isSaving}
        onSave={(value) =>
          onSaveBlock("observations", {
            observations: parseObservations(value, stageLog.observations),
          })
        }
        onRegenerateClick={() => onRegenerateClick("observations")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.observations)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.analyst_reading}
        title="Lectura del analista"
        state={stageLog.block_states.analyst_reading ?? "empty"}
        value={serializeAnalystReading(stageLog.analyst_reading)}
        editable={!!stageLog.analyst_reading}
        regenerable={!!stageLog.analyst_reading}
        hideable
        hidden={isHidden("analyst_reading")}
        maxWords={MAX_WORDS.analyst_reading}
        isSaving={isSaving}
        onSave={(value) =>
          onSaveBlock("analyst_reading", { analyst_reading: parseAnalystReading(value) })
        }
        onRegenerateClick={() => onRegenerateClick("analyst_reading")}
        onHideToggle={() => onHideToggle("analyst_reading")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.analyst_reading)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.next_segment_text}
        title="Próximo tramo"
        state={stageLog.block_states.next_segment_text ?? "empty"}
        value={stageLog.next_segment?.text ?? ""}
        editable={!!stageLog.next_segment}
        regenerable={!!stageLog.next_segment}
        maxWords={MAX_WORDS.next_segment_text}
        isSaving={isSaving}
        onSave={(value) => onSaveBlock("next_segment_text", { next_segment_text: value })}
        onRegenerateClick={() => onRegenerateClick("next_segment_text")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.next_segment_text)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.family_compass}
        title="Brújula de la familia"
        state={stageLog.block_states.family_compass ?? "empty"}
        value={serializeFamilyCompass(stageLog.family_compass)}
        maxWords={MAX_WORDS.family_compass}
        isSaving={isSaving}
        onSave={(value) =>
          onSaveBlock("family_compass", { family_compass: parseFamilyCompass(value) })
        }
        onRegenerateClick={() => onRegenerateClick("family_compass")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.family_compass)}
      />

      {showNoticeOffer && (
        <section
          aria-labelledby="change-notice-title"
          className="rounded-card bg-surface-raised px-4 py-3 shadow-card ring-1 ring-hairline"
          data-testid="change-notice-offer"
        >
          <h3
            id="change-notice-title"
            className="flex items-center gap-2 text-sm font-semibold text-charcoal"
          >
            <Megaphone size={14} aria-hidden="true" />
            Aviso de cambios en los resultados
          </h3>
          <p className="mt-1 text-xs text-mid-gray">
            Cambiamos cómo se calculan y se muestran las cifras de las
            competencias. Puedes avisarle a la familia en la nota del
            entrenador: revisas y editas el texto antes de guardarlo, y no se
            envía nada automáticamente.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setNoticeSeed((n) => n + 1)}
              className="inline-flex min-h-12 items-center gap-1.5 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90"
              data-testid="change-notice-insert"
            >
              Insertar aviso de cambios
            </button>
            <button
              type="button"
              onClick={dismiss}
              className="inline-flex min-h-12 items-center rounded-lg px-4 py-2 text-sm font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70"
              data-testid="change-notice-dismiss"
            >
              No mostrar más
            </button>
          </div>
        </section>
      )}

      <BlockCard
        key={`coach-note-${noticeSeed}`}
        startEditing={noticeSeed > 0}
        initialDraft={noticeSeed > 0 ? CHANGE_NOTICE_TEXT : undefined}
        dataBlock={BLOCK_DATA_ANCHORS.coach_note}
        title="Nota del entrenador"
        state={stageLog.block_states.coach_note ?? "empty"}
        value={stageLog.coach_note ?? ""}
        regenerable={false}
        hideable
        hidden={isHidden("coach_note")}
        maxWords={MAX_WORDS.coach_note}
        isSaving={isSaving}
        onSave={onSaveCoachNote}
        onHideToggle={() => onHideToggle("coach_note")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.coach_note)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.photos}
        title={`Fotos (${stageLog.photos.length})`}
        state={stageLog.block_states.photos ?? "empty"}
        value=""
        editable={false}
        regenerable={false}
        hideable
        hidden={isHidden("photos")}
        onHideToggle={() => onHideToggle("photos")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.photos)}
      />

      <BlockCard
        dataBlock={BLOCK_DATA_ANCHORS.badges}
        title={`Insignias (${stageLog.badges.length})`}
        state={stageLog.block_states.badges ?? "empty"}
        value=""
        editable={false}
        regenerable={false}
        hideable
        hidden={isHidden("badges")}
        onHideToggle={() => onHideToggle("badges")}
        onCardClick={() => onScrollToBlock(BLOCK_DATA_ANCHORS.badges)}
      />
    </div>
  );
}
