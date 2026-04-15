import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, UserPlus } from "lucide-react";

import { useAthletes } from "@/hooks/athletes/useAthletes";
import { useParentAthletes } from "@/hooks/parents/useParentAthletes";
import { useCreateParentAthlete } from "@/hooks/parents/useCreateParentAthlete";
import { useDeleteParentAthlete } from "@/hooks/parents/useDeleteParentAthlete";
import { FamilyRelationship } from "@/types/enums";
import { cn } from "@/lib/utils";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const inputClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

const RELATIONSHIP_LABELS: Record<FamilyRelationship, string> = {
  [FamilyRelationship.padre]: "Padre",
  [FamilyRelationship.madre]: "Madre",
  [FamilyRelationship.acudiente]: "Acudiente",
};

interface ParentAthleteAssignmentProps {
  parentId: number;
  clubId: number;
}

export function ParentAthleteAssignment({
  parentId,
  clubId,
}: ParentAthleteAssignmentProps) {
  const [showForm, setShowForm] = useState(false);
  const [selectedAthleteId, setSelectedAthleteId] = useState<string>("");
  const [selectedRelationship, setSelectedRelationship] = useState<FamilyRelationship>(
    FamilyRelationship.padre,
  );

  const relationsQuery = useParentAthletes({ parent_id: parentId });
  const athletesQuery = useAthletes({ club_id: clubId });
  const createMutation = useCreateParentAthlete();
  const deleteMutation = useDeleteParentAthlete();

  const linkedRelations = relationsQuery.data?.items ?? [];
  const allAthletes = athletesQuery.data?.items ?? [];

  const linkedAthleteIds = new Set(linkedRelations.map((r) => r.athlete_id));
  const availableAthletes = allAthletes.filter((a) => !linkedAthleteIds.has(a.id));

  function handleAdd() {
    const athleteId = Number(selectedAthleteId);
    if (!athleteId) return;

    createMutation.mutate(
      {
        parent_id: parentId,
        athlete_id: athleteId,
        relationship: selectedRelationship,
      },
      {
        onSuccess: () => {
          setShowForm(false);
          setSelectedAthleteId("");
          setSelectedRelationship(FamilyRelationship.padre);
        },
      },
    );
  }

  function handleDelete(relationId: number, athleteId: number) {
    deleteMutation.mutate({ id: relationId, athlete_id: athleteId, parent_id: parentId });
  }

  return (
    <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
      <div className="mb-4 flex items-center justify-between">
        <h3
          className="flex items-center gap-2 text-sm text-charcoal"
          style={{
            fontFamily: "'Cal Sans', system-ui, sans-serif",
            fontWeight: 600,
            letterSpacing: "0.2px",
          }}
        >
          <UserPlus size={16} />
          Atletas vinculados
        </h3>
        {availableAthletes.length > 0 && (
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            className="rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {showForm ? "Cancelar" : "+ Vincular atleta"}
          </button>
        )}
      </div>

      {/* Inline assignment form */}
      {showForm && (
        <div
          className="mb-4 rounded-lg p-4"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          <p
            className="mb-3 text-xs font-medium uppercase tracking-wide text-mid-gray"
          >
            Nueva vinculacion
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select
              value={selectedAthleteId}
              onChange={(e) => setSelectedAthleteId(e.target.value)}
              className={cn(inputClass, "flex-1")}
              style={inputStyle}
            >
              <option value="">Seleccionar atleta...</option>
              {availableAthletes.map((athlete) => (
                <option key={athlete.id} value={athlete.id}>
                  {athlete.first_name} {athlete.last_name}
                </option>
              ))}
            </select>

            <select
              value={selectedRelationship}
              onChange={(e) =>
                setSelectedRelationship(e.target.value as FamilyRelationship)
              }
              className={inputClass}
              style={inputStyle}
            >
              {Object.values(FamilyRelationship).map((rel) => (
                <option key={rel} value={rel}>
                  {RELATIONSHIP_LABELS[rel]}
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={handleAdd}
              disabled={!selectedAthleteId || createMutation.isPending}
              className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:cursor-not-allowed disabled:opacity-40"
              style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
            >
              {createMutation.isPending ? "Vinculando..." : "Vincular"}
            </button>
          </div>
          {createMutation.isError && (
            <p className="mt-2 text-xs text-red-600">
              No se pudo vincular el atleta. Intenta de nuevo.
            </p>
          )}
        </div>
      )}

      {/* Loading state */}
      {relationsQuery.isLoading && (
        <div className="space-y-2">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!relationsQuery.isLoading && linkedRelations.length === 0 && (
        <div
          className="rounded-lg px-4 py-6 text-center text-sm text-mid-gray"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px", borderStyle: "dashed" }}
        >
          No hay atletas vinculados a este padre/acudiente.
        </div>
      )}

      {/* Relations table */}
      {!relationsQuery.isLoading && linkedRelations.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-light-gray">
                <th className="pb-2 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Atleta
                </th>
                <th className="pb-2 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Relacion
                </th>
                <th className="pb-2 text-right text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-light-gray">
              {linkedRelations.map((relation) => (
                <tr key={relation.id} className="group">
                  <td className="py-2.5 font-medium text-charcoal">
                    <Link
                      to={`/athletes/${relation.athlete_id}`}
                      className="transition-opacity hover:opacity-70"
                    >
                      {relation.athlete_name}
                    </Link>
                  </td>
                  <td className="py-2.5 text-mid-gray">
                    {RELATIONSHIP_LABELS[relation.relationship]}
                  </td>
                  <td className="py-2.5 text-right">
                    <button
                      type="button"
                      onClick={() => handleDelete(relation.id, relation.athlete_id)}
                      disabled={deleteMutation.isPending}
                      className="rounded p-1 text-mid-gray transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                      title="Desvincular atleta"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
