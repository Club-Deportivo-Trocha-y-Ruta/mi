/**
 * useSessionForm — orquesta react-hook-form + snapshot inicial + diff +
 * persistencia (create/update + bulk attendance) para SessionFormPage.
 *
 * Extraído en B5 para reducir SessionFormPage por debajo de 250 LOC.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  bulkSetConvocatoria,
  useCreateTrainingSession,
  useSessionAttendance,
  useTrainingSession,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import {
  diffAthleteIds,
  diffSessionValues,
  type AthleteEntry,
  type ChangeEntry,
} from "@/lib/sessionDiff";
import {
  trainingSessionCreateSchema,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";
import type { TrainingSessionCreate } from "@/types/trainingSession.types";

import type { NotifyVariant } from "@/components/training/NotifyParentsDialog";

export interface PendingSave {
  payload: TrainingSessionCreate;
  variant: NotifyVariant;
  changes: ChangeEntry[];
  addedAthletes: AthleteEntry[];
  removedAthletes: AthleteEntry[];
  convocadosChanged: boolean;
}

export interface UseSessionFormOptions {
  mode: "create" | "edit";
  sessionId: number;
}

export function useSessionForm({ mode, sessionId }: UseSessionFormOptions) {
  const isEdit = mode === "edit";
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const sessionQuery = useTrainingSession(sessionId, isEdit);
  const attendanceQuery = useSessionAttendance(sessionId, isEdit);
  const athletesQuery = useAthletes();
  const createMutation = useCreateTrainingSession();
  const updateMutation = useUpdateTrainingSession();

  const form = useForm<TrainingSessionFormValues>({
    resolver: zodResolver(trainingSessionCreateSchema),
    shouldFocusError: true,
    defaultValues: {
      scheduled_date: "",
      scheduled_start_time: "",
      duration_min: 60,
      location: "",
      technical_focus: "",
      description: "",
      route_text: "",
      strava_url: "",
      convocados_athlete_ids: [],
    },
  });

  const initialValuesRef = useRef<TrainingSessionFormValues | null>(null);

  useEffect(() => {
    if (isEdit && sessionQuery.data && attendanceQuery.data) {
      const s = sessionQuery.data;
      const snapshot: TrainingSessionFormValues = {
        scheduled_date: s.scheduled_date,
        scheduled_start_time: s.scheduled_start_time.slice(0, 5),
        duration_min: s.duration_min,
        location: s.location,
        technical_focus: s.technical_focus,
        description: s.description,
        route_text: s.route_text ?? "",
        strava_url: s.strava_url ?? "",
        convocados_athlete_ids: attendanceQuery.data.map((a) => a.athlete_id),
      };
      form.reset(snapshot);
      initialValuesRef.current = snapshot;
    }
  }, [isEdit, sessionQuery.data, attendanceQuery.data, form]);

  const allAthletes = athletesQuery.data?.items ?? [];
  const athleteNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const a of allAthletes) {
      map.set(a.id, `${a.first_name} ${a.last_name}`.trim());
    }
    return map;
  }, [allAthletes]);

  const [pending, setPending] = useState<PendingSave | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [dialogPending, setDialogPending] = useState(false);

  function buildPayload(values: TrainingSessionFormValues): TrainingSessionCreate {
    return {
      ...values,
      route_text: values.route_text || null,
      strava_url: values.strava_url || null,
    };
  }

  function nameFor(id: number): AthleteEntry {
    return { id, name: athleteNameById.get(id) ?? `Atleta #${id}` };
  }

  async function onSubmit(values: TrainingSessionFormValues) {
    const payload = buildPayload(values);

    if (!isEdit) {
      setPending({
        payload,
        variant: "create",
        changes: [],
        addedAthletes: values.convocados_athlete_ids.map(nameFor),
        removedAthletes: [],
        convocadosChanged: false,
      });
      return;
    }

    const initial = initialValuesRef.current;
    if (!initial) return; // datos aún no cargados

    const changes = diffSessionValues(
      initial as unknown as Record<string, unknown>,
      values as unknown as Record<string, unknown>,
    );
    const attendanceDiff = diffAthleteIds(
      initial.convocados_athlete_ids,
      values.convocados_athlete_ids,
    );

    // Si no hay cambio alguno, atajo: salir sin diálogo ni mutaciones.
    if (changes.length === 0 && !attendanceDiff.changed) {
      navigate(`/training/sessions/${sessionId}`);
      return;
    }

    const variant: NotifyVariant =
      changes.length > 0 ? "update" : "attendance";

    setPending({
      payload,
      variant,
      changes,
      addedAthletes: attendanceDiff.added.map(nameFor),
      removedAthletes: attendanceDiff.removed.map(nameFor),
      convocadosChanged: attendanceDiff.changed,
    });
  }

  async function persistPending(sendNotification: boolean) {
    if (!pending) return;
    setDialogPending(true);
    setDialogError(null);
    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          id: sessionId,
          payload: { ...pending.payload, send_notification: sendNotification },
        });

        if (pending.convocadosChanged) {
          await bulkSetConvocatoria(
            sessionId,
            pending.payload.convocados_athlete_ids,
            sendNotification,
          );
          // Invalidación por namespace para alcanzar las variantes con
          // userId en el key (privacy R2: cache aislado por cuenta).
          await queryClient.invalidateQueries({
            queryKey: ["training-session-attendance"],
          });
          await queryClient.invalidateQueries({
            queryKey: ["training-session"],
          });
        }

        setPending(null);
        navigate(`/training/sessions/${sessionId}`);
      } else {
        const created = await createMutation.mutateAsync({
          ...pending.payload,
          send_notification: sendNotification,
        });
        setPending(null);
        navigate(`/training/sessions/${created.id}`);
      }
    } catch {
      setDialogError("No se pudo guardar la sesión. Intenta de nuevo.");
    } finally {
      setDialogPending(false);
    }
  }

  function handleDialogCancel() {
    if (dialogPending) return;
    setPending(null);
    setDialogError(null);
  }

  function handleCancel() {
    if (form.formState.isDirty) {
      const ok = window.confirm(
        "Tienes cambios sin guardar. ¿Salir sin guardar?",
      );
      if (!ok) return;
    }
    navigate("/training/sessions");
  }

  function onError() {
    document
      .querySelector('[aria-invalid="true"]')
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const mutationError =
    createMutation.isError || updateMutation.isError
      ? "No se pudo guardar la sesión. Intenta de nuevo."
      : null;

  return {
    form,
    sessionQuery,
    attendanceQuery,
    pending,
    dialogError,
    dialogPending,
    mutationError,
    isEdit,
    onSubmit,
    persistPending,
    handleDialogCancel,
    handleCancel,
    onError,
  };
}
