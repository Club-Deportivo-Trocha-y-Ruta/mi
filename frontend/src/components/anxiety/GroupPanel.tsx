import type { GroupMember, GroupPattern, GroupTriage } from "@/types/anxiety.types";

interface GroupPanelProps {
  triage: GroupTriage;
}

const BUCKET_LABELS: Record<GroupPattern, string> = {
  somatic_high: "Activación somática alta",
  cognitive_high: "Preocupación cognitiva alta",
  confidence_low: "Confianza baja",
  favorable: "Perfil favorable",
};

const BUCKET_ORDER: GroupPattern[] = [
  "confidence_low",
  "somatic_high",
  "cognitive_high",
  "favorable",
];

function MemberRow({ m }: { m: GroupMember }) {
  return (
    <li className="flex items-center justify-between rounded-md bg-light-gray px-2 py-1 text-sm">
      <span>Deportista #{m.athlete_id}</span>
      <span className="text-xs text-mid-gray">
        C {m.cognitive ?? "—"} · S {m.somatic ?? "—"} · A {m.selfconfidence ?? "—"}
      </span>
    </li>
  );
}

/** Triage grupal para calentamiento/huddle por patrón dominante + alertas (US5). */
export function GroupPanel({ triage }: GroupPanelProps) {
  return (
    <section
      className="rounded-xl border border-border-gray bg-white p-5"
      aria-label="Panel grupal de ansiedad"
    >
      <h3 className="mb-3 text-base font-semibold text-charcoal">
        Triage del grupo
      </h3>

      {triage.alerts.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3" role="alert">
          <h4 className="mb-1 text-sm font-medium text-amber-900">
            Alertas ({triage.alerts.length})
          </h4>
          <ul className="space-y-1">
            {triage.alerts.map((m) => (
              <MemberRow key={`alert-${m.assessment_id}`} m={m} />
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {BUCKET_ORDER.map((bucket) => {
          const members = triage.buckets[bucket] ?? [];
          return (
            <div key={bucket} className="rounded-lg border border-border-gray p-3">
              <h4 className="mb-2 text-sm font-medium text-charcoal">
                {BUCKET_LABELS[bucket]} ({members.length})
              </h4>
              {members.length === 0 ? (
                <p className="text-xs text-mid-gray">Sin deportistas.</p>
              ) : (
                <ul className="space-y-1">
                  {members.map((m) => (
                    <MemberRow key={m.assessment_id} m={m} />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default GroupPanel;
