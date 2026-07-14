import { useState } from "react";

import { mapAnxietyError } from "@/api/anxiety";
import { useInterpretation } from "@/hooks/anxiety/useAnxietyAssessments";
import type { InterpretationResponse } from "@/types/anxiety.types";

interface AnalyzeButtonProps {
  assessmentId: number;
  label?: string;
  onAnalyzed?: (result: InterpretationResponse) => void;
}

/** Botón "Analizar con IA" (US4). On-demand; tolera el cold-start de Render. */
export function AnalyzeButton({
  assessmentId,
  label = "Analizar con IA",
  onAnalyzed,
}: AnalyzeButtonProps) {
  const mutation = useInterpretation(assessmentId);
  const [error, setError] = useState<string | null>(null);

  function run() {
    setError(null);
    mutation.mutate(undefined, {
      onSuccess: (data) => onAnalyzed?.(data),
      onError: (err) => setError(mapAnxietyError(err).message),
    });
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={run}
        disabled={mutation.isPending}
        className="inline-flex min-h-10 items-center justify-center rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {mutation.isPending ? "Analizando… (puede tardar)" : label}
      </button>
      {mutation.isPending && (
        <span className="text-xs text-mid-gray">
          Si el servidor estaba inactivo, la primera respuesta puede tardar ~50 s.
        </span>
      )}
      {error && (
        <span role="alert" className="text-xs text-red-600">
          {error}
        </span>
      )}
    </div>
  );
}

export default AnalyzeButton;
