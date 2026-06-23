import { useMemo, useState } from "react";

import type { AnswerForm } from "@/types/anxiety.types";

/** Etiquetas OMNI-style 1–4 (español neutro), foco alentador, sin lenguaje clínico. */
const SCALE_LABELS: Record<number, string> = {
  1: "Nada",
  2: "Un poco",
  3: "Bastante",
  4: "Mucho",
};

interface QuestionnaireProps {
  form: AnswerForm;
  onSubmit: (answers: Record<number, number>) => void;
  isSubmitting?: boolean;
}

/**
 * Cuestionario una-pregunta-a-la-vez para el atleta (US2).
 *
 * Constitution V / privacidad: NO muestra interpretaciones ni texto clínico,
 * solo el ítem y una escala 1–4. Objetivos táctiles ≥48×48, sin scroll
 * horizontal en móvil. El texto del ítem viene de la fuente licenciada
 * (`item.text`); si no está aprovisionado se muestra un marcador neutro.
 */
export function Questionnaire({ form, onSubmit, isSubmitting }: QuestionnaireProps) {
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, number>>({});

  const total = form.items.length;
  const current = form.items[index];
  const answeredCount = useMemo(
    () => Object.keys(answers).length,
    [answers],
  );
  const isLast = index === total - 1;

  const scaleValues = useMemo(() => {
    const out: number[] = [];
    for (let v = form.scale_min; v <= form.scale_max; v += 1) out.push(v);
    return out;
  }, [form.scale_min, form.scale_max]);

  function choose(value: number) {
    setAnswers((prev) => ({ ...prev, [current.item_id]: value }));
  }

  function next() {
    if (!isLast) setIndex((i) => i + 1);
  }

  function prev() {
    if (index > 0) setIndex((i) => i - 1);
  }

  const selected = answers[current.item_id];

  return (
    <section
      className="mx-auto w-full max-w-md px-4 py-6"
      aria-label="Cuestionario previo a la carrera"
    >
      <p className="mb-4 text-sm text-slate-600">{form.intro}</p>

      <div
        className="mb-2 text-xs text-slate-500"
        aria-live="polite"
      >
        Pregunta {index + 1} de {total} · {answeredCount} respondidas
      </div>
      <div
        className="mb-5 h-2 w-full overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-label="Progreso del cuestionario"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={index + 1}
      >
        <div
          className="h-full rounded-full bg-emerald-500 transition-all"
          style={{ width: `${((index + 1) / total) * 100}%` }}
        />
      </div>

      <fieldset className="mb-6">
        <legend className="mb-4 text-base font-medium text-slate-900">
          {current.text ?? `Frase ${current.item_id}`}
        </legend>
        <div className="flex flex-col gap-2">
          {scaleValues.map((value) => {
            const active = selected === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => choose(value)}
                aria-pressed={active}
                className={[
                  "flex min-h-12 w-full items-center justify-between rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                  active
                    ? "border-emerald-600 bg-emerald-50 text-emerald-900"
                    : "border-slate-300 bg-white text-slate-700 hover:border-slate-400",
                ].join(" ")}
              >
                <span>{SCALE_LABELS[value] ?? String(value)}</span>
                <span aria-hidden className="text-xs text-slate-400">
                  {value}
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={prev}
          disabled={index === 0}
          className="min-h-12 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-40"
        >
          Anterior
        </button>
        {isLast ? (
          <button
            type="button"
            onClick={() => onSubmit(answers)}
            disabled={isSubmitting}
            className="min-h-12 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {isSubmitting ? "Enviando…" : "Enviar"}
          </button>
        ) : (
          <button
            type="button"
            onClick={next}
            className="min-h-12 rounded-lg bg-slate-900 px-5 py-2 text-sm font-medium text-white"
          >
            Siguiente
          </button>
        )}
      </div>
    </section>
  );
}

export default Questionnaire;
