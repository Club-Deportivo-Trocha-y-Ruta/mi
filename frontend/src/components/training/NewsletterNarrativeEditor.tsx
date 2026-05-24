/**
 * NewsletterNarrativeEditor — editor de narrativa IA del boletín individual.
 *
 * Permite al coach revisar y sobrescribir (override) los tres campos de narrativa
 * generados por la IA antes de aprobar el boletín.
 *
 * Reglas:
 * - Solo habilitado cuando status === "draft".
 * - Cada campo tiene un contador de caracteres con límite 500 (igual que backend).
 * - Badge de confianza IA con tooltip explicativo.
 * - Confirmación explícita si confidence === "low".
 */

import { useCallback } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, Info } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AiNarrative, NarrativeOverride } from "@/types/athleteNewsletter.types";

const MAX_CHARS = 500;

const narrativeSchema = z.object({
  strengths: z.string().max(MAX_CHARS, `Máx ${MAX_CHARS} caracteres`).optional(),
  area_to_develop: z.string().max(MAX_CHARS, `Máx ${MAX_CHARS} caracteres`).optional(),
  milestone: z.string().max(MAX_CHARS, `Máx ${MAX_CHARS} caracteres`).optional(),
});

type NarrativeFormValues = z.infer<typeof narrativeSchema>;

interface NewsletterNarrativeEditorProps {
  aiNarrative: AiNarrative | null;
  currentOverrides: NarrativeOverride | null;
  disabled?: boolean;
  isPending?: boolean;
  onSave: (overrides: NarrativeOverride) => void;
}

const CONFIDENCE_LABELS: Record<AiNarrative["confidence"], string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
};

const CONFIDENCE_TOOLTIP: Record<AiNarrative["confidence"], string> = {
  low: "La IA tuvo pocos datos para este atleta en el período (< 5 registros). Revisa y edita con cuidado antes de aprobar.",
  medium: "La IA tuvo datos suficientes pero limitados. Se recomienda revisar la narrativa.",
  high: "La IA contó con datos sólidos para este período.",
};

const CONFIDENCE_BADGE_CLASS: Record<AiNarrative["confidence"], string> = {
  low: "bg-red-100 text-red-700 border border-red-300",
  medium: "bg-yellow-100 text-yellow-700 border border-yellow-300",
  high: "bg-green-100 text-green-700 border border-green-300",
};

interface CharCounterProps {
  current: number;
  max: number;
}

function CharCounter({ current, max }: CharCounterProps) {
  const isNear = current > max * 0.85;
  const isOver = current > max;
  return (
    <span
      className={cn(
        "text-xs tabular-nums",
        isOver ? "text-red-600 font-medium" : isNear ? "text-yellow-600" : "text-mid-gray",
      )}
      aria-live="polite"
    >
      {current}/{max}
    </span>
  );
}

interface NarrativeFieldProps {
  id: string;
  label: string;
  placeholder: string;
  aiValue: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
  error?: string;
}

function NarrativeField({
  id,
  label,
  placeholder,
  aiValue,
  value,
  onChange,
  disabled,
  error,
}: NarrativeFieldProps) {
  const charCount = (value ?? "").length;
  const hasOverride = value !== "" && value !== aiValue;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <label
          htmlFor={id}
          className="text-xs font-semibold uppercase tracking-wide text-mid-gray"
        >
          {label}
          {hasOverride && (
            <span className="ml-2 rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
              Editado
            </span>
          )}
        </label>
        <CharCounter current={charCount} max={MAX_CHARS} />
      </div>

      {!disabled && aiValue && (
        <p
          className="rounded-md bg-light-gray px-3 py-2 text-xs text-mid-gray italic"
          role="note"
          data-ai-reference={label}
        >
          <span className="not-italic font-medium text-charcoal/60">IA: </span>
          {aiValue}
        </p>
      )}

      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={disabled ? aiValue || placeholder : placeholder}
        maxLength={MAX_CHARS + 10}
        rows={3}
        aria-label={label}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cn(error && "ring-2 ring-red-400/50")}
      />

      {error && (
        <p id={`${id}-error`} className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function NewsletterNarrativeEditor({
  aiNarrative,
  currentOverrides,
  disabled = false,
  isPending = false,
  onSave,
}: NewsletterNarrativeEditorProps) {
  const {
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isDirty },
  } = useForm<NarrativeFormValues>({
    resolver: zodResolver(narrativeSchema),
    defaultValues: {
      strengths: currentOverrides?.strengths ?? aiNarrative?.strengths ?? "",
      area_to_develop:
        currentOverrides?.area_to_develop ?? aiNarrative?.area_to_develop ?? "",
      milestone: currentOverrides?.milestone ?? aiNarrative?.milestone ?? "",
    },
  });

  const strengths = watch("strengths") ?? "";
  const areaToDevelop = watch("area_to_develop") ?? "";
  const milestone = watch("milestone") ?? "";

  const handleSave = useCallback(
    (values: NarrativeFormValues) => {
      const overrides: NarrativeOverride = {};
      if (values.strengths !== undefined && values.strengths !== "")
        overrides.strengths = values.strengths;
      if (values.area_to_develop !== undefined && values.area_to_develop !== "")
        overrides.area_to_develop = values.area_to_develop;
      if (values.milestone !== undefined && values.milestone !== "")
        overrides.milestone = values.milestone;
      onSave(overrides);
    },
    [onSave],
  );

  return (
    <section aria-label="Editor de narrativa IA" className="space-y-4">
      {/* Header con badge de confianza */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-charcoal">Narrativa IA</h2>
        {aiNarrative && (
          <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                className={cn(
                  "inline-flex cursor-default items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                  CONFIDENCE_BADGE_CLASS[aiNarrative.confidence],
                )}
                role="status"
                aria-label={`Confianza IA: ${CONFIDENCE_LABELS[aiNarrative.confidence]}`}
              >
                {aiNarrative.confidence === "low" && (
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                )}
                {aiNarrative.confidence !== "low" && (
                  <Info className="h-3 w-3" aria-hidden="true" />
                )}
                Confianza {CONFIDENCE_LABELS[aiNarrative.confidence]}
              </span>
            </TooltipTrigger>
            <TooltipContent side="left" className="max-w-[220px] text-xs">
              {CONFIDENCE_TOOLTIP[aiNarrative.confidence]}
            </TooltipContent>
          </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {/* Alerta de confianza baja */}
      {aiNarrative?.confidence === "low" && !disabled && (
        <div
          className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5"
          role="alert"
          data-testid="low-confidence-alert"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
          <p className="text-xs text-red-700">
            <span className="font-semibold">Confianza baja —</span> revisa y edita la narrativa antes de aprobar.
          </p>
        </div>
      )}

      {!aiNarrative && (
        <p className="text-sm text-mid-gray">Sin narrativa generada aún.</p>
      )}

      {aiNarrative && !disabled && (
        <form
          onSubmit={handleSubmit(handleSave)}
          data-testid="narrative-editor-form"
          className="space-y-4"
        >
          <NarrativeField
            id="narrative-strengths"
            label="Fortalezas"
            placeholder="Escribe las fortalezas observadas en el mes..."
            aiValue={aiNarrative.strengths}
            value={strengths}
            onChange={(v) => setValue("strengths", v, { shouldDirty: true })}
            disabled={disabled}
            error={errors.strengths?.message}
          />

          <NarrativeField
            id="narrative-area-to-develop"
            label="Area a desarrollar"
            placeholder="Describe el área técnica o física a trabajar..."
            aiValue={aiNarrative.area_to_develop}
            value={areaToDevelop}
            onChange={(v) => setValue("area_to_develop", v, { shouldDirty: true })}
            disabled={disabled}
            error={errors.area_to_develop?.message}
          />

          <NarrativeField
            id="narrative-milestone"
            label="Hito del mes"
            placeholder="Menciona un logro o avance destacado..."
            aiValue={aiNarrative.milestone}
            value={milestone}
            onChange={(v) => setValue("milestone", v, { shouldDirty: true })}
            disabled={disabled}
            error={errors.milestone?.message}
          />

          {!disabled && (
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={isPending || !isDirty}
                className="flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                data-testid="save-narrative-btn"
              >
                {isPending && (
                  <svg
                    className="h-3.5 w-3.5 animate-spin"
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
                Guardar cambios
              </button>
            </div>
          )}
        </form>
      )}

      {disabled && aiNarrative && (
        <div className="space-y-4" data-testid="narrative-readonly">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Fortalezas
            </p>
            <p className="text-sm text-charcoal">
              {currentOverrides?.strengths ?? aiNarrative.strengths}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Area a desarrollar
            </p>
            <p className="text-sm text-charcoal">
              {currentOverrides?.area_to_develop ?? aiNarrative.area_to_develop}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Hito del mes
            </p>
            <p className="text-sm text-charcoal">
              {currentOverrides?.milestone ?? aiNarrative.milestone}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
