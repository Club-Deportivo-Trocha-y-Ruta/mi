import { useCallback, useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { useUpdateAttendance } from "@/api/trainingSessions";
import type { Attendance, AttendanceStatus } from "@/types/trainingSession.types";
import type { AttendanceFormValues } from "./AttendanceTable";

// ─── Constants ───────────────────────────────────────────────────────────────

export const ATTENDANCE_FORM_DEFAULTS = {
  RPE_OMNI: 5,
  RUBRIC_SCORE: 3,
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
      rpe_omni: attendance.rpe_omni ?? ATTENDANCE_FORM_DEFAULTS.RPE_OMNI,
      rubric_effort: attendance.rubric_effort ?? ATTENDANCE_FORM_DEFAULTS.RUBRIC_SCORE,
      rubric_attitude: attendance.rubric_attitude ?? ATTENDANCE_FORM_DEFAULTS.RUBRIC_SCORE,
      rubric_technique: attendance.rubric_technique ?? ATTENDANCE_FORM_DEFAULTS.RUBRIC_SCORE,
      individual_feedback: attendance.individual_feedback ?? null,
    },
  });

  const formValues = useWatch({ control });

  const currentStatus = (formValues.status ?? attendance.status) as AttendanceStatus;
  const requiresReason = REQUIRES_REASON.includes(currentStatus);
  const allowsRubric = ALLOWS_RUBRIC.includes(currentStatus);

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
  }, [formValues, disabled]);

  return {
    control,
    register,
    setValue,
    formValues,
    savedIndicator,
    doSave,
    requiresReason,
    allowsRubric,
  };
}
