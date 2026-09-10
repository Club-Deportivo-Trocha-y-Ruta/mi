import { useEffect, useMemo, useRef } from "react";
import { X } from "lucide-react";

import { useClubCoaches } from "@/hooks/training/useClubCoaches";
import { useAuthStore } from "@/store/auth.store";

/**
 * SessionCoachesField — multi-select con chips de los entrenadores a cargo
 * de una sesión de entrenamiento (feature 041 — gobernanza multi-coach,
 * T066, contracts/session-coaches.md §10.1).
 *
 * Idioma visual calcado de `AthletesMultiSelect`
 * (`@/components/training/AthletesMultiSelect`): `<fieldset>` con `<legend>`
 * visible, chips removibles arriba y una lista de filas-toggle abajo — sin
 * Radix `Select` (research R-29 lo reserva para selección de un solo valor).
 *
 * `value`/`onChange` cargan el conjunto COMPLETO de `user_id` a cargo — el
 * backend trata `coach_user_ids` como reemplazo total, nunca un parche
 * (§3.2). El propio entrenador autenticado se prellena solo en modo
 * creación (ver el efecto abajo); en edición, quien renderiza el wizard
 * (`SessionFormPage`) ya entrega `value` con `session.coaches` cargados.
 */
interface SessionCoachesFieldProps {
  value: number[];
  onChange: (ids: number[]) => void;
  error?: string;
  /** Solo edición: acota la lista al club de la sesión (ver docstring del hook). */
  clubId?: number;
}

const HINT_TEXT = "Por defecto quedas tú. Puedes agregar a otro entrenador del club.";
const MIN_COACH_HINT = "Una sesión debe tener al menos un entrenador.";
const HINT_ID = "session-coaches-hint";
const MIN_HINT_ID = "session-coaches-min-hint";

export function SessionCoachesField({
  value,
  onChange,
  error,
  clubId,
}: SessionCoachesFieldProps) {
  const currentUser = useAuthStore((s) => s.user);
  const coachesQuery = useClubCoaches({ clubId });

  const allCoaches = coachesQuery.data?.items ?? [];

  // Prefill de creación (§10.1): si el campo llega vacío/sin inicializar y ya
  // conocemos al entrenador autenticado, lo dejamos como único seleccionado.
  // Solo dispara una vez — en edición `value` ya llega no-vacío
  // (`session.coaches`), así que este efecto nunca lo pisa.
  const didInit = useRef(false);
  useEffect(() => {
    if (didInit.current) return;
    if (value.length === 0 && currentUser) {
      didInit.current = true;
      onChange([currentUser.id]);
    }
  }, [value.length, currentUser, onChange]);

  const nameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of allCoaches) {
      map.set(c.id, `${c.first_name} ${c.last_name}`.trim());
    }
    // El entrenador autenticado puede no venir aún en la respuesta (carga en
    // curso) — usamos su nombre de sesión como respaldo para que su chip
    // nunca muestre "Entrenador #7" durante ese instante.
    if (currentUser && !map.has(currentUser.id)) {
      map.set(currentUser.id, `${currentUser.first_name} ${currentUser.last_name}`.trim());
    }
    return map;
  }, [allCoaches, currentUser]);

  // La fila-toggle solo ofrece "otros" entrenadores ACTIVOS — el propio ya
  // está representado por su chip, y asignar a alguien inactivo como NUEVO
  // entrenador está prohibido por el servidor (V4, §3.3). Un entrenador ya
  // asignado que luego se desactivó (V5) conserva su chip (viene de `value`,
  // resuelto contra TODOS los coaches vía `nameById`) aunque desaparezca de
  // esta lista — su remoción sigue disponible por el botón "Quitar" del chip.
  const others = allCoaches.filter((c) => c.id !== currentUser?.id && c.is_active);
  const sortedOthers = [
    ...others.filter((c) => value.includes(c.id)),
    ...others.filter((c) => !value.includes(c.id)),
  ];

  function toggle(id: number) {
    if (value.includes(id)) {
      // Defensa además del `disabled` del botón/checkbox: nunca vaciar del todo.
      if (value.length <= 1) return;
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  }

  if (coachesQuery.isLoading) {
    return (
      <div className="space-y-1" data-testid="session-coaches-loading">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-12 animate-pulse rounded-lg bg-light-gray" />
        ))}
      </div>
    );
  }

  if (coachesQuery.isError) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        No se pudo cargar la lista de entrenadores.{" "}
        <button
          type="button"
          onClick={() => void coachesQuery.refetch()}
          className="font-semibold underline decoration-red-300 underline-offset-2 hover:decoration-red-600"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <fieldset id="session-coaches-field" tabIndex={-1} className="space-y-2 outline-none">
      <legend className="block text-sm font-medium text-charcoal">
        Entrenadores a cargo
      </legend>
      <p id={HINT_ID} className="text-xs text-mid-gray">
        {HINT_TEXT}
      </p>

      {value.length > 0 && (
        <ul
          className="flex flex-wrap gap-1.5"
          aria-label="Entrenadores seleccionados"
          data-testid="selected-coach-chips"
        >
          {value.map((id) => {
            const isSole = value.length === 1;
            const name = nameById.get(id) ?? `Entrenador #${id}`;
            return (
              <li key={id}>
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 py-1 pl-3 pr-1 text-xs font-medium text-blue-800">
                  {name}
                  <button
                    type="button"
                    onClick={() => toggle(id)}
                    disabled={isSole}
                    aria-describedby={isSole ? MIN_HINT_ID : undefined}
                    className="flex h-5 w-5 items-center justify-center rounded-full text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                    aria-label={`Quitar a ${name}`}
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {value.length === 1 && (
        <p id={MIN_HINT_ID} className="text-xs text-mid-gray">
          {MIN_COACH_HINT}
        </p>
      )}

      <div className="max-h-56 overflow-y-auto rounded-lg bg-white shadow-ring">
        {sortedOthers.length === 0 ? (
          <p className="px-4 py-3 text-sm text-mid-gray">
            No hay otros entrenadores activos en el club.
          </p>
        ) : (
          <ul role="list">
            {sortedOthers.map((coach) => {
              const checked = value.includes(coach.id);
              const name = `${coach.first_name} ${coach.last_name}`.trim();
              return (
                <li key={coach.id}>
                  <label className="flex min-h-[48px] cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-light-gray">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(coach.id)}
                      className="h-5 w-5 rounded border-mid-gray text-charcoal"
                      aria-label={checked ? `Quitar a ${name}` : `Agregar a ${name}`}
                    />
                    <span className="flex-1 text-sm text-charcoal">{name}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
