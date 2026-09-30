/**
 * PrimaryContactSelect — marca cuál acudiente vinculado es el "contacto
 * principal" del atleta para la planilla IMDERTY (feature 047, US2,
 * FR-022/FR-022a).
 *
 * Regla del contrato (`PUT /api/athletes/{id}/primary-contact`, body
 * `{guardian_user_id: number | null}`): el teléfono de la planilla usa,
 * en orden, el teléfono propio del atleta; si no hay, el del acudiente
 * marcado como principal; si tampoco hay marca, el del primer acudiente
 * vinculado (más antiguo); si no hay ninguno, la celda queda vacía. La
 * marca es opcional — por eso siempre hay una opción "Sin marcar".
 *
 * Se guarda al vuelo (como `SensitiveDataCard`'s withdraw/record): cada
 * cambio de selección dispara el PUT de inmediato, sin botón "Guardar"
 * aparte del que ya tiene `ImdertyProfileForm` para el resto del perfil.
 */
import { toast } from "sonner";

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useUpdatePrimaryContact } from "@/hooks/useImderty";
import type { ImdertyGuardian } from "@/schemas/imderty";

export interface PrimaryContactSelectProps {
  athleteId: number;
  guardians: ImdertyGuardian[];
}

const NONE_VALUE = "__none__";

/** Extrae un mensaje de error legible para el PUT de contacto principal. */
function getPrimaryContactErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const e = err as { response?: { data?: { detail?: unknown }; status?: number } };
    if (e.response?.status === 422) {
      return "Ese usuario ya no es un acudiente vinculado a este atleta.";
    }
    if (e.response?.status === 403) return "Sin permiso para realizar esta acción.";
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return "No fue posible actualizar el contacto principal. Intenta de nuevo.";
}

export function PrimaryContactSelect({ athleteId, guardians }: PrimaryContactSelectProps) {
  const updatePrimaryContact = useUpdatePrimaryContact(athleteId);

  const currentPrimaryId = guardians.find((g) => g.is_primary_contact)?.user_id ?? null;
  const selected = currentPrimaryId != null ? String(currentPrimaryId) : NONE_VALUE;

  function handleChange(value: string) {
    if (value === selected || updatePrimaryContact.isPending) return;
    const guardianUserId = value === NONE_VALUE ? null : Number(value);
    updatePrimaryContact.mutate(
      { guardian_user_id: guardianUserId },
      {
        onSuccess: () => toast.success("Contacto principal actualizado."),
        onError: (err) => toast.error(getPrimaryContactErrorMessage(err)),
      },
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-base font-semibold text-charcoal">Contacto principal</h3>
      <p className="text-xs text-mid-gray">
        Se usa su teléfono en la planilla cuando el atleta no tiene teléfono propio.
      </p>

      {guardians.length === 0 ? (
        <p className="text-sm text-mid-gray">
          Este atleta no tiene un acudiente vinculado. Vincula uno en la sección «Padres /
          acudientes» de esta ficha para usar su teléfono en la planilla.
        </p>
      ) : (
        <RadioGroup
          value={selected}
          onValueChange={handleChange}
          aria-label="Contacto principal"
          className="space-y-2"
        >
          <label className="flex min-h-11 items-center gap-2 text-sm text-charcoal">
            <RadioGroupItem value={NONE_VALUE} disabled={updatePrimaryContact.isPending} />
            Sin marcar (se usa el primero vinculado)
          </label>
          {guardians.map((guardian) => (
            <label
              key={guardian.user_id}
              className="flex min-h-11 items-center gap-2 text-sm text-charcoal"
            >
              <RadioGroupItem
                value={String(guardian.user_id)}
                disabled={updatePrimaryContact.isPending}
              />
              <span className="flex-1">{guardian.display_name}</span>
              {!guardian.has_phone && (
                <span className="text-xs text-amber-600">Sin teléfono</span>
              )}
            </label>
          ))}
        </RadioGroup>
      )}
    </div>
  );
}
