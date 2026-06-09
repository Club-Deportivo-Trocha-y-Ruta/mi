/**
 * SessionAssistantPanel — lazy-loadable AI assistant panel.
 *
 * Flow:
 *   1. Coach writes an intent (optional free text).
 *   2. Panel calls POST /clarify → renders 0–4 ClarifyQuestionCards.
 *   3. Coach answers chips (single/multi/"Otro").
 *   4. "Generar borrador" calls POST /draft → panel emits mapped form values
 *      up to the parent via `onDraftReady`.
 *
 * Error states:
 *   - Loading → "Pensando…" spinner (no unbounded spin: bounded by ai_timeout)
 *   - Cold start hint ("Iniciando el servidor…") shown after 10 s
 *   - 503 → "El asistente no está disponible" + "Continuar manualmente" escape
 *   - 422 → recoverable inline error (coach can retry)
 */
import { useState, useRef, useEffect } from "react";
import { Loader2, AlertCircle, Sparkles } from "lucide-react";

import { useClarify, useDraft, AssistantUnavailableError } from "@/hooks/training/useSessionAssistant";
import { mapDraftToFormValues } from "@/schemas/sessionAssistant.schema";
import { buildAiSeededSet, type SeededFieldName } from "./aiSeededFields";
import { ClarifyQuestionCard } from "./ClarifyQuestionCard";

import type { ClarifyQuestion, SessionDraftResponse } from "@/api/sessionAssistant";
import type { AthleteOut } from "@/types/athlete.types";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AnswerState {
  selected_labels: string[];
  other_text: string;
}

export interface DraftReadyPayload {
  values: TrainingSessionFormValues;
  seededFields: Set<SeededFieldName>;
  draftNotes: string | null;
}

interface SessionAssistantPanelProps {
  clubId: number;
  /** Roster for resolving athlete_call_up criterion → ids. */
  roster: AthleteOut[];
  /** Current wizard form values (used as fallback when draft fields are null). */
  currentFormValues: TrainingSessionFormValues;
  /** Called when a draft is successfully generated and mapped. */
  onDraftReady: (payload: DraftReadyPayload) => void;
  /** Escape hatch: opens the empty wizard without AI draft. */
  onContinueManually: () => void;
}

// Delay after which we show the cold-start hint
const COLD_START_HINT_DELAY_MS = 10_000;

const btnPrimary =
  "inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed";
const btnSecondary =
  "inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal ring-1 ring-[rgba(34,42,53,0.12)] hover:bg-gray-50";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionAssistantPanel({
  clubId,
  roster,
  currentFormValues,
  onDraftReady,
  onContinueManually,
}: SessionAssistantPanelProps) {
  const [intentText, setIntentText] = useState("");
  const [questions, setQuestions] = useState<ClarifyQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [phase, setPhase] = useState<"intent" | "clarify" | "done">("intent");
  const [showColdStart, setShowColdStart] = useState(false);
  const coldStartTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clarifyMutation = useClarify(clubId);
  const draftMutation = useDraft(clubId);

  const isLoading = clarifyMutation.isPending || draftMutation.isPending;
  const clarifyError = clarifyMutation.error;
  const draftError = draftMutation.error;
  const activeError = draftError ?? clarifyError;

  const isUnavailable = activeError instanceof AssistantUnavailableError;

  // Cold-start hint: show after 10 s if still loading
  useEffect(() => {
    if (isLoading) {
      coldStartTimer.current = setTimeout(() => {
        setShowColdStart(true);
      }, COLD_START_HINT_DELAY_MS);
    } else {
      if (coldStartTimer.current) clearTimeout(coldStartTimer.current);
      setShowColdStart(false);
    }
    return () => {
      if (coldStartTimer.current) clearTimeout(coldStartTimer.current);
    };
  }, [isLoading]);

  // --- Handlers ---

  async function handleClarify() {
    clarifyMutation.reset();
    draftMutation.reset();
    try {
      const result = await clarifyMutation.mutateAsync({
        intent_text: intentText.trim() || null,
        selected_athlete_ids: [],
      });
      if (result.questions.length === 0) {
        // No questions → go straight to draft
        await handleGenerateDraft(result.questions);
      } else {
        setQuestions(result.questions);
        // Initialize answers map
        const initial: Record<string, AnswerState> = {};
        result.questions.forEach((q) => {
          initial[q.id] = { selected_labels: [], other_text: "" };
        });
        setAnswers(initial);
        setPhase("clarify");
      }
    } catch {
      // Error is stored in clarifyMutation.error
    }
  }

  async function handleGenerateDraft(qs: ClarifyQuestion[]) {
    draftMutation.reset();
    try {
      const draftAnswers = qs.map((q) => {
        const ans = answers[q.id] ?? { selected_labels: [], other_text: "" };
        return {
          question_id: q.id,
          selected_labels: ans.selected_labels,
          other_text: ans.other_text.trim() || null,
        };
      });
      const result: SessionDraftResponse = await draftMutation.mutateAsync({
        intent_text: intentText.trim() || null,
        selected_athlete_ids: [],
        answers: draftAnswers,
      });
      const mapped = mapDraftToFormValues(result, roster, currentFormValues);
      const seededFields = buildAiSeededSet(result);
      setPhase("done");
      onDraftReady({ values: mapped, seededFields, draftNotes: result.notes });
    } catch {
      // Error is in draftMutation.error
    }
  }

  function handleAnswerLabels(questionId: string, labels: string[]) {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { ...(prev[questionId] ?? { other_text: "" }), selected_labels: labels },
    }));
  }

  function handleAnswerOther(questionId: string, text: string) {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { ...(prev[questionId] ?? { selected_labels: [] }), other_text: text },
    }));
  }

  // --- Render ---

  return (
    <div className="space-y-5" data-testid="session-assistant-panel">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-blue-600" aria-hidden="true" />
        <h2 className="text-base font-semibold text-charcoal">
          Asistente IA para sesiones
        </h2>
      </div>
      <p className="text-sm text-mid-gray">
        Describe brevemente qué quieres trabajar y el asistente te hará unas preguntas
        rápidas para preparar un borrador de sesión.
      </p>

      {/* Intent textarea — always visible */}
      <div>
        <label
          htmlFor="assistant-intent"
          className="block text-sm font-medium text-charcoal"
        >
          ¿Qué quieres trabajar en esta sesión?{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <textarea
          id="assistant-intent"
          rows={3}
          maxLength={500}
          value={intentText}
          onChange={(e) => setIntentText(e.target.value)}
          placeholder="Ej: salida de 90 min, técnica de bajada, grupo 13-15, faltan 12 días para la válida…"
          disabled={isLoading || phase === "done"}
          className="mt-1 w-full resize-none rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-60"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          aria-describedby="assistant-intent-hint"
        />
        <p id="assistant-intent-hint" className="mt-1 text-xs text-mid-gray">
          Máximo 500 caracteres. Puedes escribir en español o inglés.
        </p>
      </div>

      {/* Phase: intent → clarify button */}
      {phase === "intent" && (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleClarify()}
            disabled={isLoading}
            className={btnPrimary}
            data-testid="assistant-ask-btn"
          >
            {isLoading ? (
              <>
                <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                Pensando…
              </>
            ) : (
              <>
                <Sparkles size={16} aria-hidden="true" />
                Preguntar al asistente
              </>
            )}
          </button>
          <button
            type="button"
            onClick={onContinueManually}
            className={btnSecondary}
            data-testid="assistant-manual-btn"
          >
            Continuar manualmente
          </button>
        </div>
      )}

      {/* Phase: clarify → question cards + generate draft */}
      {phase === "clarify" && questions.length > 0 && (
        <div className="space-y-4">
          <p className="text-sm font-medium text-charcoal">
            Responde las siguientes preguntas para personalizar el borrador:
          </p>
          {questions.map((q) => (
            <ClarifyQuestionCard
              key={q.id}
              question={q}
              selectedLabels={answers[q.id]?.selected_labels ?? []}
              otherText={answers[q.id]?.other_text ?? ""}
              onSelectedLabelsChange={(labels) => handleAnswerLabels(q.id, labels)}
              onOtherTextChange={(text) => handleAnswerOther(q.id, text)}
            />
          ))}

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void handleGenerateDraft(questions)}
              disabled={isLoading}
              className={btnPrimary}
              data-testid="assistant-draft-btn"
            >
              {isLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                  Generando borrador…
                </>
              ) : (
                <>
                  <Sparkles size={16} aria-hidden="true" />
                  Generar borrador
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onContinueManually}
              className={btnSecondary}
              data-testid="assistant-skip-btn"
            >
              Continuar manualmente
            </button>
          </div>
        </div>
      )}

      {/* Cold-start hint */}
      {isLoading && showColdStart && (
        <p
          className="text-xs text-mid-gray"
          role="status"
          data-testid="assistant-cold-start"
          aria-live="polite"
        >
          Iniciando el servidor, puede tardar hasta 30 segundos…
        </p>
      )}

      {/* Error: 503 unavailable */}
      {isUnavailable && !isLoading && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4"
          data-testid="assistant-unavailable"
        >
          <div className="flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5 shrink-0 text-amber-700" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold text-amber-900">
                El asistente no está disponible
              </p>
              <p className="text-xs text-amber-800">
                El servicio de IA no está disponible en este momento. Puedes
                continuar creando la sesión manualmente.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onContinueManually}
              className={btnPrimary}
              data-testid="assistant-fallback-manual-btn"
            >
              Continuar manualmente
            </button>
            <button
              type="button"
              onClick={() => {
                clarifyMutation.reset();
                draftMutation.reset();
                setPhase("intent");
                setQuestions([]);
                setAnswers({});
              }}
              className={btnSecondary}
              data-testid="assistant-retry-btn"
            >
              Reintentar
            </button>
          </div>
        </div>
      )}

      {/* Error: 422 validation (recoverable) */}
      {!isUnavailable && activeError && !isLoading && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4"
          data-testid="assistant-validation-error"
        >
          <AlertCircle size={16} className="mt-0.5 shrink-0 text-red-600" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-red-800">
              No se pudo procesar la solicitud
            </p>
            <p className="text-xs text-red-700">
              {activeError.message || "Verifica tu intención y vuelve a intentarlo."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
