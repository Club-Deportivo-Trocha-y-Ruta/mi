import { useState } from "react";
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";

import { AthletesMultiSelect } from "@/components/training/AthletesMultiSelect";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import type { Audience, AudienceType } from "@/types/calendar.types";

// FCC categories — hardcoded per plan
const FCC_CATEGORIES = [
  "Pre-Infantil A",
  "Pre-Infantil B",
  "Infantil A",
  "Infantil B",
  "Pre-juvenil A",
  "Pre-juvenil B",
  "Junior",
  "Elite",
];

interface AudienceSelectorProps {
  value: Audience[];
  onChange: (audiences: Audience[]) => void;
  error?: string;
}

const labelClass = "block text-sm font-medium text-charcoal";
const selectClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const selectStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

export function AudienceSelector({ value, onChange, error }: AudienceSelectorProps) {
  const [selectedType, setSelectedType] = useState<AudienceType>("all_club");
  const [selectedCategory, setSelectedCategory] = useState<string>(FCC_CATEGORIES[0]);
  const [selectedAthleteIds, setSelectedAthleteIds] = useState<number[]>([]);
  const [selectedAthleteId, setSelectedAthleteId] = useState<number | null>(null);

  const athletesQuery = useAthletes();
  const athletes = athletesQuery.data?.items ?? [];

  function handleTypeChange(type: AudienceType) {
    setSelectedType(type);
    // Reset audience-specific fields
    setSelectedCategory(FCC_CATEGORIES[0]);
    setSelectedAthleteIds([]);
    setSelectedAthleteId(null);
  }

  function buildCurrentAudience(): Audience | null {
    switch (selectedType) {
      case "all_club":
        return { audience_type: "all_club", audience_value: {} as Record<string, never> };
      case "category":
        return {
          audience_type: "category",
          audience_value: { category: selectedCategory },
        };
      case "athlete_list":
        if (selectedAthleteIds.length === 0) return null;
        return {
          audience_type: "athlete_list",
          audience_value: { athlete_ids: selectedAthleteIds },
        };
      case "individual":
        if (!selectedAthleteId) return null;
        return {
          audience_type: "individual",
          audience_value: { athlete_id: selectedAthleteId },
        };
    }
  }

  function handleAdd() {
    const aud = buildCurrentAudience();
    if (!aud) return;
    // Avoid duplicates of the same type+value
    onChange([...value, aud]);
  }

  function handleRemove(idx: number) {
    onChange(value.filter((_, i) => i !== idx));
  }

  function audienceLabel(aud: Audience): string {
    switch (aud.audience_type) {
      case "all_club":
        return "Todo el club";
      case "category":
        return `Categoría: ${aud.audience_value.category}`;
      case "athlete_list":
        return `${aud.audience_value.athlete_ids.length} atleta(s) seleccionado(s)`;
      case "individual":
        return `Atleta individual (id: ${aud.audience_value.athlete_id})`;
    }
  }

  return (
    <div className="space-y-4">
      {/* Radio group for audience type */}
      <RadioGroupPrimitive.Root
        value={selectedType}
        onValueChange={(v) => handleTypeChange(v as AudienceType)}
        aria-label="Tipo de audiencia"
        className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {(
          [
            { value: "all_club", label: "Todo el club" },
            { value: "category", label: "Categoría" },
            { value: "athlete_list", label: "Lista de atletas" },
            { value: "individual", label: "Atleta individual" },
          ] as { value: AudienceType; label: string }[]
        ).map((opt) => (
          <RadioGroupPrimitive.Item
            key={opt.value}
            value={opt.value}
            id={`audience-type-${opt.value}`}
            className="flex cursor-pointer items-center justify-center rounded-lg px-2 py-2 text-xs font-medium text-charcoal transition-colors data-[state=checked]:bg-charcoal data-[state=checked]:text-white data-[state=unchecked]:bg-white data-[state=unchecked]:hover:bg-light-gray"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            <RadioGroupPrimitive.Indicator className="hidden" />
            <label htmlFor={`audience-type-${opt.value}`} className="cursor-pointer">
              {opt.label}
            </label>
          </RadioGroupPrimitive.Item>
        ))}
      </RadioGroupPrimitive.Root>

      {/* Conditional fields */}
      {selectedType === "category" && (
        <div>
          <label htmlFor="audience-category-select" className={labelClass}>
            Categoría FCC
          </label>
          <select
            id="audience-category-select"
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className={selectClass}
            style={selectStyle}
          >
            {FCC_CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      )}

      {selectedType === "athlete_list" && (
        <div>
          <p className={labelClass}>Atletas</p>
          <AthletesMultiSelect
            value={selectedAthleteIds}
            onChange={setSelectedAthleteIds}
          />
        </div>
      )}

      {selectedType === "individual" && (
        <div>
          <label htmlFor="audience-individual-select" className={labelClass}>
            Atleta
          </label>
          <select
            id="audience-individual-select"
            value={selectedAthleteId ?? ""}
            onChange={(e) =>
              setSelectedAthleteId(e.target.value ? Number(e.target.value) : null)
            }
            className={selectClass}
            style={selectStyle}
          >
            <option value="">Selecciona un atleta</option>
            {athletes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.first_name} {a.last_name}
              </option>
            ))}
          </select>
        </div>
      )}

      <button
        type="button"
        onClick={handleAdd}
        className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
      >
        + Agregar audiencia
      </button>

      {/* Added audiences */}
      {value.length > 0 && (
        <ul className="space-y-2">
          {value.map((aud, idx) => (
            <li
              key={idx}
              className="flex items-center justify-between rounded-lg bg-light-gray px-3 py-2 text-sm text-charcoal"
            >
              <span>{audienceLabel(aud)}</span>
              <button
                type="button"
                onClick={() => handleRemove(idx)}
                className="ml-3 text-xs text-red-600 transition-opacity hover:opacity-70"
                aria-label={`Eliminar audiencia ${audienceLabel(aud)}`}
              >
                Eliminar
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
