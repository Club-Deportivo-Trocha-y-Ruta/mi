/**
 * useImportWizardState — state machine del wizard de importación.
 *
 * Centraliza los 9 useState que vivían en ImportWizard:
 *  - step (1|2|3)
 *  - parseResult, resultadosPdf, generalPdf
 *  - resolutions (Map competitor_normalized_name → athlete_id|null)
 *  - onlyPending, step1Error
 *  - revisionReason, revisionReasonTouched
 *
 * Devuelve también `resetToStep1` para reiniciar el wizard.
 *
 * Extraído en B5 para reducir LOC del archivo principal y permitir tests
 * unitarios del flujo sin montar todo el árbol UI.
 */
import { useCallback, useState } from "react";

import type {
  ImportParseResponse,
} from "@/types/raceImports.types";

export type WizardStep = 1 | 2 | 3;

export interface ImportWizardState {
  // Step + parse
  step: WizardStep;
  parseResult: ImportParseResponse | null;
  resultadosPdf: File | null;
  generalPdf: File | null;
  // Matches resolution
  resolutions: Record<string, number | null>;
  onlyPending: boolean;
  // UI errors
  step1Error: string | null;
  // F-UP-REV5: revision reason
  revisionReason: string;
  revisionReasonTouched: boolean;
}

export interface ImportWizardActions {
  setStep: (s: WizardStep) => void;
  setParseResult: (p: ImportParseResponse | null) => void;
  setResultadosPdf: (f: File | null) => void;
  setGeneralPdf: (f: File | null) => void;
  setResolutions: React.Dispatch<
    React.SetStateAction<Record<string, number | null>>
  >;
  setOnlyPending: (v: boolean) => void;
  setStep1Error: (msg: string | null) => void;
  setRevisionReason: (s: string) => void;
  setRevisionReasonTouched: (v: boolean) => void;
  /** Reinicia el wizard al paso 1 conservando defaults. */
  resetToStep1: () => void;
}

export function useImportWizardState(): ImportWizardState & ImportWizardActions {
  const [step, setStep] = useState<WizardStep>(1);
  const [parseResult, setParseResult] = useState<ImportParseResponse | null>(
    null,
  );
  const [resultadosPdf, setResultadosPdf] = useState<File | null>(null);
  const [generalPdf, setGeneralPdf] = useState<File | null>(null);
  const [resolutions, setResolutions] = useState<
    Record<string, number | null>
  >({});
  const [onlyPending, setOnlyPending] = useState(false);
  const [step1Error, setStep1Error] = useState<string | null>(null);
  const [revisionReason, setRevisionReason] = useState("");
  const [revisionReasonTouched, setRevisionReasonTouched] = useState(false);

  const resetToStep1 = useCallback(() => {
    setStep(1);
    setParseResult(null);
    setResultadosPdf(null);
    setGeneralPdf(null);
    setResolutions({});
    setOnlyPending(false);
    setStep1Error(null);
    setRevisionReason("");
    setRevisionReasonTouched(false);
  }, []);

  return {
    step,
    parseResult,
    resultadosPdf,
    generalPdf,
    resolutions,
    onlyPending,
    step1Error,
    revisionReason,
    revisionReasonTouched,
    setStep,
    setParseResult,
    setResultadosPdf,
    setGeneralPdf,
    setResolutions,
    setOnlyPending,
    setStep1Error,
    setRevisionReason,
    setRevisionReasonTouched,
    resetToStep1,
  };
}
