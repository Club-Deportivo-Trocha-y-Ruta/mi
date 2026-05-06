import { useState } from "react";
import { CheckCircle, Clock, Mail, XCircle } from "lucide-react";

import { useCreateParentInvite, useParentInvites } from "@/hooks/parents/useParentInvites";
import type { ParentInviteOut } from "@/types/parent.types";
import type { FamilyRelationship } from "@/types/enums";
import { cn } from "@/lib/utils";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const inputClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 flex-1";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

type InviteStatus = "used" | "expired" | "pending";

function getInviteStatus(invite: ParentInviteOut): InviteStatus {
  if (invite.used) return "used";
  if (new Date(invite.expires_at) < new Date()) return "expired";
  return "pending";
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function InviteStatusBadge({ status }: { status: InviteStatus }) {
  if (status === "pending") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
        <Clock size={11} />
        Pendiente
      </span>
    );
  }
  if (status === "used") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
        <CheckCircle size={11} />
        Usado
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">
      <XCircle size={11} />
      Vencido
    </span>
  );
}

interface ParentInviteManagerProps {
  athleteId: number;
  athleteName: string;
  /**
   * ID del usuario padre pre-creado por el coach. Cuando está presente, el
   * backend ata la invitación a ese usuario y consume_invite hace UPDATE en
   * lugar de INSERT — evita duplicados.
   */
  parentUserId?: number;
  /** Tipo de parentesco registrado en el vínculo. Se persiste en el invite. */
  relationshipType?: FamilyRelationship;
  /** Email pre-cargado (si el coach ya lo capturó al crear el padre). */
  defaultEmail?: string;
}

export function ParentInviteManager({
  athleteId,
  athleteName,
  parentUserId,
  relationshipType,
  defaultEmail = "",
}: ParentInviteManagerProps) {
  const [email, setEmail] = useState(defaultEmail);

  const invitesQuery = useParentInvites(athleteId);
  const createInviteMutation = useCreateParentInvite();

  const invites = invitesQuery.data ?? [];
  // Most recent invite first
  const sortedInvites = [...invites].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  // "used" represents an invite that the parent already consumed (account
  // created). Prefer it over a stale "pending" because once any invite is
  // consumed, the parent is registered and no further invitations are needed
  // for this athlete relationship.
  const usedInvite = sortedInvites.find((i) => i.used) ?? null;
  const pendingInvite =
    sortedInvites.find((i) => getInviteStatus(i) === "pending") ?? null;
  const showAccountActivated = usedInvite !== null;
  const showPendingPanel = !showAccountActivated && pendingInvite !== null;
  const showSendForm = !showAccountActivated && !showPendingPanel;

  function handleSend(resendEmail?: string) {
    const targetEmail = resendEmail ?? email.trim();
    if (!targetEmail) return;

    createInviteMutation.mutate(
      {
        athlete_id: athleteId,
        email: targetEmail,
        parent_user_id: parentUserId ?? null,
        relationship_type: relationshipType ?? null,
      },
      {
        onSuccess: () => {
          if (!resendEmail) setEmail("");
        },
      },
    );
  }

  return (
    <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
      <h4
        className="mb-1 flex items-center gap-2 text-sm text-charcoal"
        style={{
          fontFamily: "'Cal Sans', system-ui, sans-serif",
          fontWeight: 600,
          letterSpacing: "0.2px",
        }}
      >
        <Mail size={15} />
        Invitacion — {athleteName}
      </h4>
      {!showAccountActivated && (
        <p className="mb-4 text-xs text-mid-gray">
          Invita al padre/madre/acudiente de este atleta a crear su cuenta en el portal.
        </p>
      )}

      {/* Account already activated — parent consumed the invite */}
      {showAccountActivated && usedInvite && (
        <div
          className="mb-4 rounded-lg bg-green-50 px-4 py-3 text-sm"
          style={{ boxShadow: "rgba(34, 197, 94, 0.25) 0px 0px 0px 1px" }}
        >
          <div className="flex items-start gap-2">
            <CheckCircle size={14} className="mt-0.5 shrink-0 text-green-700" />
            <div className="space-y-0.5">
              <p className="text-xs font-medium text-green-800">
                Cuenta activada
              </p>
              <p className="text-xs text-green-700">
                <span className="font-medium">{usedInvite.email}</span> ya
                completó el registro y tiene acceso al portal.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Pending invite — show resend action */}
      {showPendingPanel && pendingInvite && (
        <div
          className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm"
          style={{ boxShadow: "rgba(251, 191, 36, 0.25) 0px 0px 0px 1px" }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="space-y-0.5">
              <p className="text-xs font-medium text-amber-800">Invitacion activa</p>
              <p className="text-xs text-amber-700">
                Enviada a:{" "}
                <span className="font-medium">{pendingInvite.email}</span>
              </p>
              <p className="text-xs text-amber-700">
                Vence: {formatDate(pendingInvite.expires_at)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleSend(pendingInvite.email)}
              disabled={createInviteMutation.isPending}
              className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-80 disabled:opacity-40"
            >
              {createInviteMutation.isPending ? "Reenviando..." : "Reenviar"}
            </button>
          </div>
        </div>
      )}

      {/* Send invite form — only when no active invite and no activated account */}
      {showSendForm && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="correo@ejemplo.com"
            className={inputClass}
            style={inputStyle}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSend();
            }}
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={!email.trim() || createInviteMutation.isPending}
            className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {createInviteMutation.isPending ? "Enviando..." : "Enviar invitacion"}
          </button>
        </div>
      )}

      {createInviteMutation.isError && (
        <p className="mt-2 text-xs text-red-600">
          No se pudo enviar la invitacion. Verifica el correo e intenta de nuevo.
        </p>
      )}

      {createInviteMutation.isSuccess && (
        <p className="mt-2 text-xs text-green-600">
          Invitacion enviada correctamente.
        </p>
      )}

      {/* Invite history */}
      {sortedInvites.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mid-gray">
            Historial de invitaciones
          </p>
          <div className="space-y-1.5">
            {sortedInvites.map((invite) => {
              const status = getInviteStatus(invite);
              return (
                <div
                  key={invite.id}
                  className={cn(
                    "flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs",
                    status === "pending"
                      ? "bg-amber-50"
                      : "bg-light-gray",
                  )}
                >
                  <div className="space-y-0.5">
                    <span className="font-medium text-charcoal">{invite.email}</span>
                    <p className="text-mid-gray">
                      Enviada: {formatDate(invite.created_at)} · Vence:{" "}
                      {formatDate(invite.expires_at)}
                    </p>
                  </div>
                  <InviteStatusBadge status={status} />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
