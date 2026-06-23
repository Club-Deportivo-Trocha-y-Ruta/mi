import { useState } from "react";
import { useParams } from "react-router-dom";

import { mapAnxietyError } from "@/api/anxiety";
import { Questionnaire } from "@/components/anxiety/Questionnaire";
import {
  useAnswerForm,
  useSubmitAnswers,
} from "@/hooks/anxiety/useAnxietyAssessments";
import type { AnswerResult } from "@/types/anxiety.types";

/**
 * Ruta pública (sin login) donde el atleta responde vía token de un solo uso.
 * Estados: cargando, enlace usado/expirado (410), error, cuestionario, gracias.
 */
export function AnswerPage() {
  const { token = "" } = useParams<{ token: string }>();
  const form = useAnswerForm(token);
  const submit = useSubmitAnswers(token);
  const [result, setResult] = useState<AnswerResult | null>(null);

  if (form.isLoading) {
    return (
      <Centered>
        <p className="text-sm text-slate-600">Cargando…</p>
      </Centered>
    );
  }

  if (form.isError) {
    const info = mapAnxietyError(form.error);
    return (
      <Centered>
        <h1 className="mb-2 text-xl font-semibold text-slate-900">
          {info.kind === "token_gone" ? "Enlace no disponible" : "Algo salió mal"}
        </h1>
        <p className="text-sm text-slate-600">{info.message}</p>
      </Centered>
    );
  }

  if (result) {
    return (
      <Centered>
        <h1 className="mb-2 text-xl font-semibold text-emerald-700">¡Listo!</h1>
        <p className="text-sm text-slate-600">{result.short_message}</p>
      </Centered>
    );
  }

  if (!form.data) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <Questionnaire
        form={form.data}
        isSubmitting={submit.isPending}
        onSubmit={(answers) =>
          submit.mutate(answers, { onSuccess: (r) => setResult(r) })
        }
      />
      {submit.isError && (
        <p role="alert" className="mx-auto max-w-md px-4 text-sm text-red-600">
          {mapAnxietyError(submit.error).message}
        </p>
      )}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="max-w-md text-center">{children}</div>
    </div>
  );
}

export default AnswerPage;
