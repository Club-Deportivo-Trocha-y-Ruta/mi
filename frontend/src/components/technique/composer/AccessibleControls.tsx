/**
 * AccessibleControls — keyboard- and screen-reader-accessible DOM controls
 * for the gymkhana circuit composer (T031 / FR-018 / WCAG 2.1 AA).
 *
 * This component is INDEPENDENT of the Konva canvas — it is pure DOM
 * (buttons, inputs, a list) and works with assistive technology on tablet.
 * It operates on the same elements state via props/callbacks.
 *
 * Capabilities:
 *   - Add an element by kind (select + button)
 *   - Select an element from the list (aria role="listbox")
 *   - Nudge position: ↑↓←→ arrow buttons in 1-unit steps
 *   - Adjust rotation: +15° / -15° buttons
 *   - Set line style (dashed / solid) when kind = 'line'
 *   - Edit label (Phase B anti-PII validated via piiGuard)
 *   - Remove the selected element
 *
 * Privacy (FR-019): the label field shows a PII guard error inline; the UI
 * never prompts for an athlete name.
 */

import { useId, useState } from "react";

import type { CircuitElementKind } from "@/types/technique.types";
import type { ComposedElement } from "./KonvaCanvas";
import { validatePhaseBLabel } from "./piiGuard";

// ---------------------------------------------------------------------------
// Spanish labels for element kinds (FR-020)
// ---------------------------------------------------------------------------

const KIND_LABELS: Record<CircuitElementKind, string> = {
  cone:  "Cono",
  line:  "Trayecto",
  gate:  "Puerta",
  mine:  "Mina",
  beam:  "Equilibrio (viga)",
  ring:  "Círculo de la muerte",
  arrow: "Dirección de recorrido",
};

const ALL_KINDS: CircuitElementKind[] = [
  "cone", "line", "gate", "mine", "beam", "ring", "arrow",
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface AccessibleControlsProps {
  elements: ComposedElement[];
  selectedId: string | null;
  canvasWidth: number;
  canvasHeight: number;
  onSelect: (id: string | null) => void;
  onAdd: (kind: CircuitElementKind) => void;
  onChange: (id: string, updates: Partial<Omit<ComposedElement, "_id" | "kind">>) => void;
  onRemove: (id: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AccessibleControls({
  elements,
  selectedId,
  canvasWidth,
  canvasHeight,
  onSelect,
  onAdd,
  onChange,
  onRemove,
}: AccessibleControlsProps) {
  const uid = useId();
  const pickerId = `${uid}-kind-picker`;
  const listId = `${uid}-el-list`;
  const labelId = `${uid}-el-label`;

  const [kindPick, setKindPick] = useState<CircuitElementKind>("cone");
  const [labelError, setLabelError] = useState<string | null>(null);

  const selected = elements.find((e) => e._id === selectedId) ?? null;

  // ── Label validation ──
  function handleLabelChange(value: string) {
    const err = validatePhaseBLabel(value);
    setLabelError(err);
    if (!err && selectedId) {
      onChange(selectedId, { label: value || undefined });
    }
  }

  // ── Nudge helpers ──
  const NUDGE = 2; // logical units per step

  function nudge(dx: number, dy: number) {
    if (!selected) return;
    onChange(selected._id, {
      x: Math.max(0, Math.min(selected.x + dx, canvasWidth)),
      y: Math.max(0, Math.min(selected.y + dy, canvasHeight)),
    });
  }

  function rotate(delta: number) {
    if (!selected) return;
    onChange(selected._id, {
      rotation: ((selected.rotation ?? 0) + delta + 360) % 360,
    });
  }

  const btnBase =
    "min-h-[44px] min-w-[44px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-40 disabled:cursor-not-allowed";

  const iconBtn =
    "min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg border border-slate-300 bg-white text-slate-600 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <section
      aria-label="Controles del compositor (accesible sin ratón)"
      className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4"
    >
      {/* ── Add element ── */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Agregar elemento
        </p>
        <div className="flex flex-wrap gap-2">
          <label htmlFor={pickerId} className="sr-only">
            Tipo de elemento
          </label>
          <select
            id={pickerId}
            value={kindPick}
            onChange={(e) => setKindPick(e.target.value as CircuitElementKind)}
            className="min-h-[44px] flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {ALL_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onAdd(kindPick)}
            className={btnBase}
          >
            + Agregar
          </button>
        </div>
      </div>

      {/* ── Element list ── */}
      {elements.length > 0 && (
        <div>
          <p
            id={`${listId}-label`}
            className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500"
          >
            Elementos en el circuito ({elements.length})
          </p>
          <ul
            id={listId}
            role="listbox"
            aria-labelledby={`${listId}-label`}
            aria-activedescendant={selectedId ? `${uid}-el-${selectedId}` : undefined}
            tabIndex={0}
            className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            onKeyDown={(e) => {
              const ids = elements.map((el) => el._id);
              const cur = ids.indexOf(selectedId ?? "");
              if (e.key === "ArrowDown") {
                e.preventDefault();
                onSelect(ids[Math.min(cur + 1, ids.length - 1)]);
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                onSelect(ids[Math.max(cur - 1, 0)]);
              } else if (e.key === "Delete" || e.key === "Backspace") {
                if (selectedId) onRemove(selectedId);
              }
            }}
          >
            {elements.map((el, idx) => (
              <li
                key={el._id}
                id={`${uid}-el-${el._id}`}
                role="option"
                aria-selected={el._id === selectedId}
                onClick={() => onSelect(el._id)}
                className={[
                  "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                  el._id === selectedId
                    ? "bg-primary text-white"
                    : "text-slate-700 hover:bg-slate-100",
                ].join(" ")}
              >
                <span className="shrink-0 text-xs font-mono text-slate-400" aria-hidden="true">
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <span className="flex-1 truncate">
                  {KIND_LABELS[el.kind]}
                  {el.label && (
                    <span className="ml-1 opacity-70">— {el.label}</span>
                  )}
                </span>
                <span
                  className="shrink-0 text-xs opacity-60"
                  aria-label={`Posición x:${Math.round(el.x)} y:${Math.round(el.y)}`}
                >
                  ({Math.round(el.x)}, {Math.round(el.y)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Selected element controls ── */}
      {selected && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Elemento seleccionado: {KIND_LABELS[selected.kind]}
          </p>

          {/* Position nudge */}
          <div>
            <p className="mb-1.5 text-xs text-slate-600">Mover posición ({NUDGE} unidades)</p>
            <div className="grid grid-cols-3 gap-1" style={{ maxWidth: 148 }}>
              {/* Row 1: up */}
              <div />
              <button
                type="button"
                aria-label="Mover arriba"
                onClick={() => nudge(0, -NUDGE)}
                className={iconBtn}
              >
                ↑
              </button>
              <div />
              {/* Row 2: left / right */}
              <button
                type="button"
                aria-label="Mover a la izquierda"
                onClick={() => nudge(-NUDGE, 0)}
                className={iconBtn}
              >
                ←
              </button>
              <button
                type="button"
                aria-label="Mover abajo"
                onClick={() => nudge(0, NUDGE)}
                className={iconBtn}
              >
                ↓
              </button>
              <button
                type="button"
                aria-label="Mover a la derecha"
                onClick={() => nudge(NUDGE, 0)}
                className={iconBtn}
              >
                →
              </button>
            </div>
          </div>

          {/* Rotation */}
          <div>
            <p className="mb-1.5 text-xs text-slate-600">Rotar (15°)</p>
            <div className="flex gap-2">
              <button
                type="button"
                aria-label="Rotar 15 grados antihorario"
                onClick={() => rotate(-15)}
                className={iconBtn}
              >
                ↺
              </button>
              <span className="min-h-[44px] flex items-center px-3 text-sm tabular-nums text-slate-700">
                {Math.round(selected.rotation ?? 0)}°
              </span>
              <button
                type="button"
                aria-label="Rotar 15 grados horario"
                onClick={() => rotate(15)}
                className={iconBtn}
              >
                ↻
              </button>
            </div>
          </div>

          {/* Line style (dashed/solid) — only for line kind */}
          {selected.kind === "line" && (
            <div>
              <p className="mb-1.5 text-xs text-slate-600">Estilo de trayecto</p>
              <div className="flex gap-2" role="group" aria-label="Estilo de trayecto">
                <button
                  type="button"
                  aria-pressed={selected.style !== "solid"}
                  onClick={() => onChange(selected._id, { style: "dashed" })}
                  className={[
                    btnBase,
                    (selected.style !== "solid")
                      ? "border-primary bg-primary/10 text-primary"
                      : "",
                  ].join(" ")}
                >
                  Guía / libre (----)
                </button>
                <button
                  type="button"
                  aria-pressed={selected.style === "solid"}
                  onClick={() => onChange(selected._id, { style: "solid" })}
                  className={[
                    btnBase,
                    selected.style === "solid"
                      ? "border-primary bg-primary/10 text-primary"
                      : "",
                  ].join(" ")}
                >
                  Técnico (────)
                </button>
              </div>
            </div>
          )}

          {/* Label (Phase B — anti-PII guarded) */}
          <div>
            <label
              htmlFor={labelId}
              className="mb-1 block text-xs text-slate-600"
            >
              Etiqueta del elemento{" "}
              <span className="text-slate-400">(opcional, sin nombres)</span>
            </label>
            <input
              id={labelId}
              type="text"
              defaultValue={selected.label ?? ""}
              maxLength={40}
              placeholder="Ej: Salida, #1, Meta…"
              aria-describedby={labelError ? `${labelId}-err` : undefined}
              onChange={(e) => handleLabelChange(e.target.value)}
              className={[
                "min-h-[44px] w-full rounded-lg border px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2",
                labelError
                  ? "border-red-400 focus:ring-red-400/50"
                  : "border-slate-300 focus:ring-primary/50",
              ].join(" ")}
            />
            {labelError && (
              <p id={`${labelId}-err`} role="alert" className="mt-1 text-xs text-red-600">
                {labelError}
              </p>
            )}
          </div>

          {/* Remove */}
          <button
            type="button"
            aria-label={`Eliminar elemento ${KIND_LABELS[selected.kind]}`}
            onClick={() => {
              onRemove(selected._id);
              onSelect(null);
            }}
            className="min-h-[44px] rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50"
          >
            Eliminar elemento
          </button>
        </div>
      )}

      {elements.length === 0 && (
        <p className="text-xs italic text-slate-400">
          Sin elementos. Agrega al menos uno desde el selector de arriba.
        </p>
      )}
    </section>
  );
}

export default AccessibleControls;
