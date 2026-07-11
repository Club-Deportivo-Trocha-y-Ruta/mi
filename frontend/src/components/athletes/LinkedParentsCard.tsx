import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Mail, Phone, UserRound } from "lucide-react";

import { useParentAthletes } from "@/hooks/parents/useParentAthletes";
import { useParentInvites } from "@/hooks/parents/useParentInvites";
import { cn, maskPhone } from "@/lib/utils";
import type { ParentAthleteOut, ParentInviteOut } from "@/types/parent.types";
import type { FamilyRelationship } from "@/types/enums";

// ─── Sub-components (internal, not exported) ──────────────────────────────────

function RelationshipBadge({ relationship }: { relationship: FamilyRelationship }) {
  const palette: Record<FamilyRelationship, string> = {
    padre: "bg-sky-100 text-sky-700",
    madre: "bg-violet-100 text-violet-700",
    acudiente: "bg-stone-100 text-stone-700",
  };
  const label: Record<FamilyRelationship, string> = {
    padre: "Padre",
    madre: "Madre",
    acudiente: "Acudiente",
  };
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        palette[relationship],
      )}
    >
      {label[relationship]}
    </span>
  );
}

function ParentRow({
  parent,
  canViewContactDetails,
}: {
  parent: ParentAthleteOut;
  canViewContactDetails: boolean;
}) {
  const nameParts = parent.parent_name.trim().split(/\s+/);
  const initials =
    nameParts.length >= 2
      ? `${nameParts[0].charAt(0)}${nameParts[nameParts.length - 1].charAt(0)}`.toUpperCase()
      : parent.parent_name.slice(0, 2).toUpperCase();

  return (
    <div className="flex items-start gap-3 py-3">
      {/* Avatar */}
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-light-gray text-sm font-semibold text-charcoal">
        {initials}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/parents/${parent.parent_id}`}
            className="text-sm font-semibold text-charcoal transition-opacity hover:opacity-70"
          >
            {parent.parent_name}
          </Link>
          <RelationshipBadge relationship={parent.relationship} />
        </div>

        {canViewContactDetails ? (
          <dl className="mt-1.5 grid grid-cols-[auto_1fr] items-center gap-x-2 gap-y-0.5">
            <dt className="flex items-center text-xs text-mid-gray">
              <Mail size={12} className="mr-1" />
            </dt>
            <dd className="truncate text-xs text-mid-gray">
              {parent.parent_email ?? "—"}
            </dd>
            <dt className="flex items-center text-xs text-mid-gray">
              <Phone size={12} className="mr-1" />
            </dt>
            <dd className="text-xs text-mid-gray">
              {maskPhone(parent.parent_phone)}
            </dd>
          </dl>
        ) : (
          <Link
            to={`/parents/${parent.parent_id}`}
            className="mt-1 text-xs font-medium text-link-blue transition-opacity hover:opacity-70"
          >
            Ver perfil →
          </Link>
        )}
      </div>
    </div>
  );
}

function isInvitePending(invite: ParentInviteOut): boolean {
  return !invite.used && new Date(invite.expires_at) >= new Date();
}

function InviteFooter({
  athleteId,
  pendingInviteEmail,
}: {
  athleteId: number;
  pendingInviteEmail: string | null;
}) {
  if (pendingInviteEmail) {
    return (
      <div className="flex flex-col items-end gap-1 pt-1">
        <span className="cursor-not-allowed text-sm font-medium text-mid-gray">
          Invitación pendiente
        </span>
        <span className="text-xs text-mid-gray">
          Enviada a <span className="font-medium">{pendingInviteEmail}</span>
        </span>
      </div>
    );
  }
  return (
    <div className="flex justify-end pt-1">
      <Link
        to="/parents"
        state={{ athleteId }}
        className="text-sm font-medium text-link-blue transition-opacity hover:opacity-70"
      >
        Invitar acudiente →
      </Link>
    </div>
  );
}

function ParentRowSkeleton() {
  return (
    <div className="flex items-start gap-3 py-3">
      <div className="h-9 w-9 shrink-0 animate-pulse rounded-full bg-light-gray" />
      <div className="flex-1 space-y-2 pt-1">
        <div className="h-4 w-36 animate-pulse rounded bg-light-gray" />
        <div className="h-3 w-48 animate-pulse rounded bg-light-gray" />
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface LinkedParentsCardProps {
  athleteId: number;
  canViewContactDetails?: boolean;
  canInvite?: boolean;
  defaultExpanded?: boolean;
}

export function LinkedParentsCard({
  athleteId,
  canViewContactDetails = true,
  canInvite = true,
  defaultExpanded = false,
}: LinkedParentsCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const { data, isLoading, isError, refetch } = useParentAthletes(
    isExpanded ? { athlete_id: athleteId } : undefined,
  );
  const invitesQuery = useParentInvites(isExpanded ? athleteId : undefined);

  const parents = data?.items ?? [];
  const count: number | null = data?.total ?? null;
  const pendingInvite =
    invitesQuery.data?.find(isInvitePending) ?? null;
  const pendingInviteEmail = pendingInvite?.email ?? null;

  return (
    <div className={cn("overflow-hidden rounded-xl bg-white", "shadow-card")}>
      {/* Header — always visible, acts as toggle */}
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between px-5 py-4 transition-colors hover:bg-light-gray/40"
        aria-expanded={isExpanded}
      >
        <span className="font-display text-sm text-charcoal">
          <UserRound size={15} className="mr-2 inline-block text-mid-gray" />
          Padres / acudientes
        </span>

        <span className="flex items-center gap-2">
          {count !== null && (
            <span className="text-xs text-mid-gray">
              {count} vinculado{count !== 1 ? "s" : ""}
            </span>
          )}
          <ChevronDown
            size={16}
            className={cn(
              "text-mid-gray transition-transform duration-200",
              isExpanded && "rotate-180",
            )}
          />
        </span>
      </button>

      {/* Body — only when expanded */}
      {isExpanded && (
        <div
          className="px-5 pb-4"
          style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
        >
          {/* Loading */}
          {isLoading && (
            <div>
              <ParentRowSkeleton />
              <ParentRowSkeleton />
            </div>
          )}

          {/* Error */}
          {isError && !isLoading && (
            <p className="py-3 text-sm text-mid-gray">
              No se pudo cargar.{" "}
              <button
                type="button"
                onClick={() => refetch()}
                className="font-medium text-charcoal underline underline-offset-2 transition-opacity hover:opacity-70"
              >
                Reintentar
              </button>
            </p>
          )}

          {/* Empty state */}
          {!isLoading && !isError && parents.length === 0 && (
            <div className="py-3 space-y-2">
              <p className="text-sm text-mid-gray">
                Ningún padre o acudiente vinculado.
              </p>
              <p className="text-sm text-mid-gray">
                Invita a un acudiente para que pueda ver el progreso del atleta.
              </p>
              {canInvite && (
                <div className="flex justify-end pt-1">
                  <InviteFooter
                    athleteId={athleteId}
                    pendingInviteEmail={pendingInviteEmail}
                  />
                </div>
              )}
            </div>
          )}

          {/* Parents list */}
          {!isLoading && !isError && parents.length > 0 && (
            <div>
              {parents.map((parent, index) => (
                <div
                  key={parent.id}
                  className={cn(
                    index > 0 && "border-t border-[rgba(34,42,53,0.06)]",
                  )}
                >
                  <ParentRow
                    parent={parent}
                    canViewContactDetails={canViewContactDetails}
                  />
                </div>
              ))}

              {canInvite && parents.length < 3 && (
                <div
                  className="border-t border-[rgba(34,42,53,0.06)] pt-3"
                >
                  <InviteFooter
                    athleteId={athleteId}
                    pendingInviteEmail={pendingInviteEmail}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
