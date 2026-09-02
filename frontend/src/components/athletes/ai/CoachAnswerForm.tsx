/**
 * CoachAnswerForm — formulario para que el coach responda la
 * `coach_question` de un insight v3 y/o lo califique (feature 037, US4).
 *
 * - Textarea ≤ 1000 caracteres con contador.
 * - Dos botones de calificación accesibles (👍 Útil / 👎 No útil) con
 *   `aria-pressed` reflejando `coach_rating`.
 * - Envía con `useAnswerInsight` (actualización optimista) — se puede
 *   enviar solo texto, solo calificación, o ambos.
 * - Diseñado para montarse en el slot `footer` de `InsightV3Card` (T301,
 *   Wave 3) — este componente no depende de esa card, solo recibe
 *   `athleteId`/`insightId`/valores iniciales.
 */
import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAnswerInsight } from "@/hooks/athletes/useAnswerInsight";
import { extractErrorDetail } from "@/lib/apiError";

const MAX_LENGTH = 1000;
const ERROR_FALLBACK = "No se pudo guardar la respuesta. Intenta de nuevo.";

export interface CoachAnswerFormProps {
  athleteId: number;
  insightId: number;
  initialAnswer?: string | null;
  initialRating?: number | null;
}

export function CoachAnswerForm({
  athleteId,
  insightId,
  initialAnswer,
  initialRating,
}: CoachAnswerFormProps) {
  const mutation = useAnswerInsight(athleteId);
  const [text, setText] = useState(initialAnswer ?? "");
  const [rating, setRating] = useState<number | null>(initialRating ?? null);
  const [saved, setSaved] = useState(false);

  const trimmed = text.trim();
  const hasTextChange = trimmed !== (initialAnswer ?? "").trim();

  const submit = async (nextRating?: number | null) => {
    const effectiveRating = nextRating !== undefined ? nextRating : rating;
    const body: { answer_text?: string; rating?: number } = {};
    if (hasTextChange && trimmed.length > 0) body.answer_text = trimmed;
    if (effectiveRating !== null && effectiveRating !== initialRating) {
      body.rating = effectiveRating;
    }
    if (body.answer_text === undefined && body.rating === undefined) return;

    setSaved(false);
    try {
      await mutation.mutateAsync({ insightId, body });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      // El mensaje de error se muestra abajo vía extractErrorDetail.
    }
  };

  const handleRatingClick = (value: 1 | -1) => {
    const next = rating === value ? null : value;
    setRating(next);
    void submit(next);
  };

  return (
    <div className="flex flex-col gap-3" data-testid="coach-answer-form">
      <div className="flex flex-col gap-1">
        <label htmlFor={`coach-answer-${insightId}`} className="text-sm font-medium">
          Tu respuesta
        </label>
        <Textarea
          id={`coach-answer-${insightId}`}
          value={text}
          maxLength={MAX_LENGTH}
          onChange={(e) => setText(e.target.value)}
          placeholder="Escribe tu respuesta a la pregunta del analista…"
          className="min-h-24"
        />
        <span className="text-xs text-muted-foreground self-end">
          {text.length}/{MAX_LENGTH}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant={rating === 1 ? "default" : "outline"}
          size="sm"
          aria-pressed={rating === 1}
          aria-label="Marcar insight como útil"
          onClick={() => handleRatingClick(1)}
          className="min-h-10"
        >
          <ThumbsUp size={14} aria-hidden="true" />
          Útil
        </Button>
        <Button
          type="button"
          variant={rating === -1 ? "default" : "outline"}
          size="sm"
          aria-pressed={rating === -1}
          aria-label="Marcar insight como no útil"
          onClick={() => handleRatingClick(-1)}
          className="min-h-10"
        >
          <ThumbsDown size={14} aria-hidden="true" />
          No útil
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={!hasTextChange || trimmed.length === 0 || mutation.isPending}
          onClick={() => void submit()}
          className="ml-auto min-h-10"
        >
          {mutation.isPending ? "Guardando…" : "Guardar respuesta"}
        </Button>
      </div>

      <div role="status" aria-live="polite" className="text-xs">
        {saved && !mutation.isError && (
          <span className="text-emerald-600">Respuesta guardada.</span>
        )}
        {mutation.isError && (
          <span className="text-destructive">
            {extractErrorDetail(mutation.error, ERROR_FALLBACK)}
          </span>
        )}
      </div>
    </div>
  );
}
