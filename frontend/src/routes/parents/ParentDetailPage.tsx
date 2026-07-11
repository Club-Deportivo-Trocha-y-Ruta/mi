import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Trash2, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { ParentContactInfo } from "@/components/parents/ParentContactInfo";
import { ParentAthleteAssignment } from "@/components/parents/ParentAthleteAssignment";
import { ParentInviteManager } from "@/components/parents/ParentInviteManager";
import { useDeleteParentUser } from "@/hooks/parents/useDeleteParentUser";
import { useParentAthletes } from "@/hooks/parents/useParentAthletes";
import { useParentUsers } from "@/hooks/parents/useParentUsers";
import { useAuthStore } from "@/store/auth.store";

function StatCard({
  icon: Icon,
  label,
  value,
  subtitle,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <div className="rounded-xl bg-white p-4 shadow-card">
      <div className="flex items-center gap-2 text-mid-gray">
        <Icon size={16} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-1.5 text-2xl font-bold text-charcoal">{value}</p>
      {subtitle && <p className="mt-0.5 text-xs text-mid-gray">{subtitle}</p>}
    </div>
  );
}

export function ParentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const parentId = Number(id);

  const user = useAuthStore((state) => state.user);
  const clubId = user?.club_ids?.[0] ?? 0;

  const parentsQuery = useParentUsers();
  const parent = parentsQuery.data?.items.find((p) => p.id === parentId) ?? null;

  const relationsQuery = useParentAthletes({ parent_id: parentId });
  const linkedCount = relationsQuery.data?.items.length ?? 0;
  const linkedRelations = relationsQuery.data?.items ?? [];

  const deleteMutation = useDeleteParentUser();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDelete = () => {
    setDeleteError(null);
    deleteMutation.mutate(parentId, {
      onSuccess: () => {
        setDeleteOpen(false);
        navigate("/parents");
      },
      onError: () => {
        setDeleteError("No se pudo eliminar el padre/acudiente. Intenta de nuevo.");
      },
    });
  };

  // Loading skeleton
  if (parentsQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-6 w-48 animate-pulse rounded-lg bg-light-gray" />
        <div className="h-28 animate-pulse rounded-xl bg-light-gray" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="h-48 animate-pulse rounded-xl bg-light-gray" />
          <div className="h-48 animate-pulse rounded-xl bg-light-gray" />
        </div>
      </section>
    );
  }

  // Not found
  if (parentsQuery.isError || (!parentsQuery.isLoading && !parent)) {
    return (
      <section className="space-y-3">
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Padre / acudiente no encontrado
        </h1>
        <p className="text-sm text-mid-gray">
          No existe un padre con ese ID o no tienes permisos para verlo.
        </p>
        <Link
          to="/parents"
          className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        >
          Volver a la lista
        </Link>
      </section>
    );
  }

  if (!parent) return null;

  return (
    <section className="space-y-5">
      {/* Breadcrumb + title */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <Link
            to="/parents"
            className="text-sm text-mid-gray transition-opacity hover:opacity-70"
          >
            &larr; Padres
          </Link>
          <h1
            className="font-display mt-1 text-2xl text-charcoal"
          >
            {parent.first_name} {parent.last_name}
          </h1>
        </div>
        <button
          type="button"
          onClick={() => {
            setDeleteError(null);
            setDeleteOpen(true);
          }}
          className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
        >
          <Trash2 size={14} />
          Eliminar
        </button>
      </div>

      {/* Stat card row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={Users}
          label="Atletas vinculados"
          value={relationsQuery.isLoading ? "—" : String(linkedCount)}
          subtitle={
            linkedCount === 1
              ? "1 atleta en el club"
              : `${linkedCount} atletas en el club`
          }
        />
        {/* Placeholder cols so the stat card doesn't stretch to full width on desktop */}
        <div className="col-span-1 hidden lg:col-span-3 lg:block" />
      </div>

      {/* Two-column layout: contact info + assignment */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ParentContactInfo parent={parent} />
        <ParentAthleteAssignment parentId={parentId} clubId={clubId} />
      </div>

      {/* Invite managers — one per linked athlete */}
      {linkedRelations.length > 0 && (
        <div className="space-y-3">
          <h2
            className="font-display text-base text-charcoal"
            style={{ letterSpacing: "0.2px" }}
          >
            Invitaciones al portal
          </h2>
          {linkedRelations.map((relation) => (
            <ParentInviteManager
              key={relation.athlete_id}
              athleteId={relation.athlete_id}
              athleteName={relation.athlete_name}
              parentUserId={parentId}
              relationshipType={relation.relationship}
              defaultEmail={parent?.email ?? ""}
            />
          ))}
        </div>
      )}

      {/* Empty invite section when no athletes linked */}
      {!relationsQuery.isLoading && linkedRelations.length === 0 && (
        <div className="rounded-xl bg-white px-5 py-8 text-center shadow-card">
          <p className="text-sm text-mid-gray">
            Vincula al menos un atleta para poder generar invitaciones al portal.
          </p>
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        title="Eliminar padre/acudiente"
        description={
          <>
            <span className="font-medium text-charcoal">
              {parent.first_name} {parent.last_name}
            </span>
            <br />
            Se eliminarán de forma permanente el padre/acudiente, sus vínculos con atletas, su membresía al club y sus consentimientos otorgados. Las invitaciones que haya consumido quedarán como anónimas. Esta acción no se puede deshacer.
          </>
        }
        confirmLabel="Sí, eliminar"
        tone="danger"
        isPending={deleteMutation.isPending}
        errorMessage={deleteError ?? undefined}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
      />
    </section>
  );
}
