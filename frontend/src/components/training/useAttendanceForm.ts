import { useCallback, useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { useUpdateAttendance } from "@/api/trainingSessions";
import type { Attendance, AttendanceStatus } from "@/types/trainingSession.types";
import type { AttendanceFormValues } from "./AttendanceTable";

// ─── Constants ───────────────────────────────────────────────────────────────

export const ATTENDANCE_FORM_DEFAULTS = {
  DEBOUNCE_MS: 500,
} as const;

export const REQUIRES_REASON: AttendanceStatus[] = ["ausente", "justificado", "lesionado"];
export const ALLOWS_RUBRIC: AttendanceStatus[] = ["presente", "tarde"];

// ─── Hook ────────────────────────────────────────────────────────────────────

export interface UseAttendanceFormReturn {
  control: ReturnType<typeof useForm<AttendanceFormValues>>["control"];
  register: ReturnType<typeof useForm<AttendanceFormValues>>["register"];
  setValue: ReturnType<typeof useForm<AttendanceFormValues>>["setValue"];
  formValues: Partial<AttendanceFormValues>;
  savedIndicator: "saved" | "error" | null;
  doSave: (values: AttendanceFormValues) => void;
  requiresReason: boolean;
  allowsRubric: boolean;
  needsReasonAlert: boolean;
}

export function useAttendanceForm(
  attendance: Attendance,
  sessionId: number,
  disabled: boolean | undefined,
): UseAttendanceFormReturn {
  const [savedIndicator, setSavedIndicator] = useState<"saved" | "error" | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const mutation = useUpdateAttendance(sessionId);

  const { control, register, setValue } = useForm<AttendanceFormValues>({
    defaultValues: {
      status: attendance.status,
      excuse_reason: attendance.excuse_reason ?? null,
      // RPE OMNI y las 3 rúbricas son OPCIONALES (pedido del coach: una
      // sesión de recuperación con fisioterapia no tiene ni RPE ni técnica)
      // — el default es `null`, nunca un valor "neutro" inventado. Antes se
      // rellenaban con 5/3/3/3 y ese relleno se autoguardaba en cuanto se
      // tocaba cualquier campo de la fila (p. ej. el estado), fabricando
      // evaluaciones que el coach nunca registró.
      rpe_omni: attendance.rpe_omni ?? null,
      rubric_effort: attendance.rubric_effort ?? null,
      rubric_attitude: attendance.rubric_attitude ?? null,
      rubric_technique: attendance.rubric_technique ?? null,
      individual_feedback: attendance.individual_feedback ?? null,
    },
  });

  const formValues = useWatch({ control });

  const currentStatus = (formValues.status ?? attendance.status) as AttendanceStatus;
  const requiresReason = REQUIRES_REASON.includes(currentStatus);
  const allowsRubric = ALLOWS_RUBRIC.includes(currentStatus);
  const needsReasonAlert =
    requiresReason && !(formValues.excuse_reason ?? "").trim();

  const doSave = useCallback(
    (values: AttendanceFormValues) => {
      const payload: AttendanceFormValues = { ...values };
      if (!ALLOWS_RUBRIC.includes(values.status)) {
        payload.rpe_omni = null;
        payload.rubric_effort = null;
        payload.rubric_attitude = null;
        payload.rubric_technique = null;
        payload.individual_feedback = null;
      }
      if (!REQUIRES_REASON.includes(values.status)) {
        payload.excuse_reason = null;
      }
      mutation.mutate(
        { athleteId: attendance.athlete_id, payload },
        {
          onSuccess: () => {
            setSavedIndicator("saved");
            setTimeout(() => setSavedIndicator(null), 1500);
          },
          onError: () => setSavedIndicator("error"),
        },
      );
    },
    [attendance.athlete_id, mutation],
  );

  // H6 fix: no serializar en el array de deps — stringify ocurre UNA vez dentro del efecto
  const lastSyncedRef = useRef<string>(JSON.stringify(formValues));
  useEffect(() => {
    if (disabled) return;
    // Gate: si requiere razón pero está vacía, no auto-guardar (evita 422 garantizado)
    if (needsReasonAlert) return;
    const current = JSON.stringify(formValues);
    if (current === lastSyncedRef.current) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      lastSyncedRef.current = current;
      doSave(formValues as AttendanceFormValues);
    }, ATTENDANCE_FORM_DEFAULTS.DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // formValues reference from useWatch changes each render; stringify runs only inside effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formValues, disabled, needsReasonAlert]);

  return {
    control,
    register,
    setValue,
    formValues,
    savedIndicator,
    doSave,
    requiresReason,
    allowsRubric,
    needsReasonAlert,
  };
}
