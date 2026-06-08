/**
 * ClarifyQuestionCard — renders a single clarifying question as selectable chips.
 *
 * Supports:
 *   - `multi_select=false` → ToggleGroup type="single" (≤1 selected)
 *   - `multi_select=true`  → ToggleGroup type="multiple" (n selected)
 *   - `allow_other=true`   → extra "Otro" chip that reveals a free-text input
 *
 * Controlled via React Hook Form Controller (external form). The parent
 * passes a `Controller`-rendered `field` prop so this card stays pure.
 */
import { useState } from "react";
import type { ClarifyQuestion } from "@/api/sessionAssistant";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

const chipClass =
  "min-h-[48px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-2 text-xs font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white";

const inputClass =
  "mt-2 w-full min-h-[48px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

interface ClarifyQuestionCardProps {
  question: ClarifyQuestion;
  /** Currently selected option labels (excluding "Otro"). */
  selectedLabels: string[];
  /** Current free-text value for "Otro". */
  otherText: string;
  onSelectedLabelsChange: (labels: string[]) => void;
  onOtherTextChange: (text: string) => void;
}

const OTRO_LABEL = "Otro";

export function ClarifyQuestionCard({
  question,
  selectedLabels,
  otherText,
  onSelectedLabelsChange,
  onOtherTextChange,
}: ClarifyQuestionCardProps) {
  const [otherSelected, setOtherSelected] = useState(false);

  function handleSingleChange(value: string) {
    if (value === OTRO_LABEL) {
      setOtherSelected(true);
      onSelectedLabelsChange([]);
    } else if (value) {
      setOtherSelected(false);
      onSelectedLabelsChange([value]);
    } else {
      // Deselect
      setOtherSelected(false);
      onSelectedLabelsChange([]);
    }
  }

  function handleMultipleChange(values: string[]) {
    const hasOtro = values.includes(OTRO_LABEL);
    setOtherSelected(hasOtro);
    onSelectedLabelsChange(values.filter((v) => v !== OTRO_LABEL));
  }

  // For single-select, the "current" value of the ToggleGroup
  const singleValue = otherSelected
    ? OTRO_LABEL
    : selectedLabels.length > 0
      ? selectedLabels[0]
      : "";

  // For multi-select
  const multiValue = [...selectedLabels, ...(otherSelected ? [OTRO_LABEL] : [])];

  const headerId = `clarify-q-${question.id}-header`;
  const questionId = `clarify-q-${question.id}-question`;
  const otherInputId = `clarify-q-${question.id}-other`;

  return (
    <div
      className="space-y-2 rounded-xl border border-[rgba(34,42,53,0.08)] bg-white p-4"
      data-testid={`clarify-question-${question.id}`}
    >
      {/* Header badge */}
      <span
        id={headerId}
        className="inline-block rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700"
      >
        {question.header}
      </span>

      {/* Question text */}
      <p id={questionId} className="text-sm font-medium text-charcoal">
        {question.question}
      </p>

      {/* Chips */}
      {question.multi_select ? (
        <ToggleGroup
          type="multiple"
          value={multiValue}
          onValueChange={handleMultipleChange}
          className="flex flex-wrap gap-1.5"
          aria-labelledby={questionId}
          data-testid={`clarify-chips-${question.id}`}
        >
          {question.options.map((opt) => (
            <ToggleGroupItem
              key={opt.label}
              value={opt.label}
              className={chipClass}
              title={opt.description}
              aria-label={`${opt.label} — ${opt.description}`}
            >
              {opt.label}
            </ToggleGroupItem>
          ))}
          {question.allow_other && (
            <ToggleGroupItem
              value={OTRO_LABEL}
              className={chipClass}
              aria-label="Otro (texto libre)"
              data-testid={`clarify-otro-chip-${question.id}`}
            >
              Otro
            </ToggleGroupItem>
          )}
        </ToggleGroup>
      ) : (
        <ToggleGroup
          type="single"
          value={singleValue}
          onValueChange={handleSingleChange}
          className="flex flex-wrap gap-1.5"
          aria-labelledby={questionId}
          data-testid={`clarify-chips-${question.id}`}
        >
          {question.options.map((opt) => (
            <ToggleGroupItem
              key={opt.label}
              value={opt.label}
              className={chipClass}
              title={opt.description}
              aria-label={`${opt.label} — ${opt.description}`}
            >
              {opt.label}
            </ToggleGroupItem>
          ))}
          {question.allow_other && (
            <ToggleGroupItem
              value={OTRO_LABEL}
              className={chipClass}
              aria-label="Otro (texto libre)"
              data-testid={`clarify-otro-chip-${question.id}`}
            >
              Otro
            </ToggleGroupItem>
          )}
        </ToggleGroup>
      )}

      {/* "Otro" free-text input — revealed when Otro chip is selected */}
      {otherSelected && question.allow_other && (
        <div>
          <label
            htmlFor={otherInputId}
            className="block text-xs font-medium text-charcoal"
          >
            Especifica:
          </label>
          <input
            id={otherInputId}
            type="text"
            value={otherText}
            onChange={(e) => onOtherTextChange(e.target.value)}
            placeholder="Describe tu opción…"
            maxLength={300}
            className={inputClass}
            style={inputStyle}
            aria-describedby={questionId}
            data-testid={`clarify-other-input-${question.id}`}
          />
        </div>
      )}

      {/* Option descriptions as sub-labels for selected items (accessibility) */}
      {selectedLabels.length > 0 && (
        <ul className="space-y-0.5" aria-live="polite" aria-atomic="false">
          {selectedLabels.map((label) => {
            const opt = question.options.find((o) => o.label === label);
            return opt ? (
              <li key={label} className="text-xs text-mid-gray">
                <span className="font-medium">{opt.label}:</span> {opt.description}
              </li>
            ) : null;
          })}
        </ul>
      )}
    </div>
  );
}
