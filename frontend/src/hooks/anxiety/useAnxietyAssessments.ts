import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAssessment,
  createBatch,
  getAnswerForm,
  getAssessment,
  interpretAssessment,
  recomputeAssessment,
  submitAnswers,
} from "@/api/anxiety";
import type {
  AnswerForm,
  AssessmentCreated,
  AssessmentRead,
  BatchCreated,
  CreateAssessmentInput,
  CreateBatchInput,
  InterpretationResponse,
} from "@/types/anxiety.types";

export const anxietyKeys = {
  assessment: (id: number) => ["anxiety", "assessment", id] as const,
  answerForm: (token: string) => ["anxiety", "answer", token] as const,
};

/** POST /assessments — crea una evaluación individual. */
export function useCreateAssessment() {
  return useMutation<AssessmentCreated, unknown, CreateAssessmentInput>({
    mutationKey: ["anxiety", "create"],
    mutationFn: (input) => createAssessment(input),
  });
}

/** POST /assessments/batch — crea evaluaciones para un grupo. */
export function useCreateBatch() {
  return useMutation<BatchCreated, unknown, CreateBatchInput>({
    mutationKey: ["anxiety", "create-batch"],
    mutationFn: (input) => createBatch(input),
  });
}

/** GET /answer/{token} — formulario del atleta (sin auth). */
export function useAnswerForm(token: string) {
  return useQuery<AnswerForm>({
    queryKey: anxietyKeys.answerForm(token),
    queryFn: () => getAnswerForm(token),
    enabled: token.length > 0,
    retry: false,
    staleTime: Infinity,
  });
}

/** POST /answer/{token} — envía respuestas (sin auth). */
export function useSubmitAnswers(token: string) {
  return useMutation({
    mutationKey: ["anxiety", "submit", token],
    mutationFn: (answers: Record<number, number>) =>
      submitAnswers(token, answers),
  });
}

/** GET /assessments/{id} */
export function useAssessment(id: number, enabled = true) {
  return useQuery<AssessmentRead>({
    queryKey: anxietyKeys.assessment(id),
    queryFn: () => getAssessment(id),
    enabled: enabled && id > 0,
  });
}

/** POST /assessments/{id}/recompute */
export function useRecompute(id: number) {
  const queryClient = useQueryClient();
  return useMutation<AssessmentRead, unknown, void>({
    mutationKey: ["anxiety", "recompute", id],
    mutationFn: () => recomputeAssessment(id),
    onSuccess: (data) => {
      queryClient.setQueryData(anxietyKeys.assessment(id), data);
    },
  });
}

/** POST /assessments/{id}/interpret — on-demand, cacheado en backend. */
export function useInterpretation(id: number) {
  const queryClient = useQueryClient();
  return useMutation<InterpretationResponse, unknown, { signal?: AbortSignal } | void>({
    mutationKey: ["anxiety", "interpret", id],
    mutationFn: (vars) => interpretAssessment(id, { signal: vars?.signal }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: anxietyKeys.assessment(id) });
    },
  });
}
