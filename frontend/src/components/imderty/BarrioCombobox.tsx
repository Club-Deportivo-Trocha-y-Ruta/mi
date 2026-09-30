/**
 * BarrioCombobox — selector accesible del catálogo de barrios de Yumbo
 * (feature 047, IMDERTY). Sigue el mismo patrón que
 * `components/ai/AthleteCombobox.tsx`: dropdown casero (button + div
 * posicionado) sin Radix Popover ni cmdk, con las garantías de
 * accesibilidad implementadas a mano (role=combobox, listbox,
 * aria-activedescendant, teclado, click-outside).
 *
 * Particularidades del dominio (contrato §Barrio catalog, data-model
 * `imderty_barrios`):
 *  - El valor no es solo un id: `barrio_id` y `other_municipality` son
 *    mutuamente excluyentes (CHECK en BD), así que el combobox emite ambos
 *    campos juntos en `BarrioComboboxValue`.
 *  - «Otro municipio» es una opción fija (no viene del catálogo) que deja
 *    comuna/zona vacías.
 *  - Cada barrio muestra su zona (comuna 1–4 o zona rural) junto al nombre,
 *    porque la comuna/zona nunca se escribe a mano (FR-002).
 *  - Búsqueda case-insensitive y diacritic-insensitive («yumbo» encuentra
 *    «YUMBO»).
 *  - Solo trae barrios activos (`useBarrios()` sin `includeInactive`).
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { AlertCircle, Check, ChevronsUpDown, Search, X } from "lucide-react";

import { useBarrios } from "@/hooks/useImderty";
import { cn } from "@/lib/utils";
import type { Barrio } from "@/schemas/imderty";

export interface BarrioComboboxValue {
  /** Id del barrio del catálogo, o `null` si no hay selección o es "otro municipio". */
  barrioId: number | null;
  /** `true` ⇒ "Otro municipio" (comuna/zona vacías); mutuamente excluyente con `barrioId`. */
  otherMunicipality: boolean;
}

interface BarrioComboboxProps {
  value: BarrioComboboxValue;
  onChange: (value: BarrioComboboxValue) => void;
  placeholder?: string;
  label?: string;
  error?: string;
  id?: string;
  className?: string;
  "data-testid"?: string;
}

const OTHER_MUNICIPALITY_LABEL = "Otro municipio";

/** Normaliza string para comparar sin acentos ni mayúsculas. */
function normalize(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

/** "1"–"4" ⇒ "Comuna N"; las zonas rurales ya vienen como texto legible. */
function zoneLabel(zone: string): string {
  return /^[1-4]$/.test(zone) ? `Comuna ${zone}` : zone;
}

function displayLabel(barrio: Barrio): string {
  return `${barrio.name} · ${zoneLabel(barrio.zone)}`;
}

type ComboItem =
  | { kind: "other-municipality" }
  | { kind: "barrio"; barrio: Barrio };

export function BarrioCombobox({
  value,
  onChange,
  placeholder = "Selecciona un barrio",
  label,
  error,
  id,
  className,
  "data-testid": dataTestId = "barrio-combobox",
}: BarrioComboboxProps) {
  const reactId = useMemo(
    () => id ?? `barrio-combobox-${Math.random().toString(36).slice(2, 8)}`,
    [id],
  );
  const listboxId = `${reactId}-listbox`;

  const barriosQuery = useBarrios();
  const barrios = barriosQuery.data ?? [];

  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Click fuera del componente → cerrar.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent | TouchEvent) {
      const target = e.target as Node | null;
      if (target && containerRef.current && !containerRef.current.contains(target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
    };
  }, [open]);

  // Reset búsqueda al cerrar el panel.
  useEffect(() => {
    if (!open) {
      setSearch("");
      setActiveIndex(0);
    }
  }, [open]);

  // Auto-foco al input cuando abre.
  useEffect(() => {
    if (open) {
      const t = setTimeout(
        () => inputRef.current?.focus({ preventScroll: true }),
        10,
      );
      return () => clearTimeout(t);
    }
  }, [open]);

  const selectedBarrio = useMemo<Barrio | null>(() => {
    if (value.otherMunicipality || value.barrioId == null) return null;
    return barrios.find((b) => b.id === value.barrioId) ?? null;
  }, [value, barrios]);

  const filteredBarrios = useMemo(() => {
    const q = normalize(search);
    if (!q) return barrios;
    return barrios.filter((b) => normalize(b.name).includes(q));
  }, [barrios, search]);

  const items = useMemo<ComboItem[]>(() => {
    const q = normalize(search);
    const showOther = !q || normalize(OTHER_MUNICIPALITY_LABEL).includes(q);
    return [
      ...(showOther ? [{ kind: "other-municipality" as const }] : []),
      ...filteredBarrios.map((barrio) => ({ kind: "barrio" as const, barrio })),
    ];
  }, [search, filteredBarrios]);

  const clampedActive =
    items.length === 0 ? 0 : Math.min(activeIndex, items.length - 1);

  const handleSelect = useCallback(
    (next: BarrioComboboxValue) => {
      onChange(next);
      setOpen(false);
      setTimeout(() => triggerRef.current?.focus(), 0);
    },
    [onChange],
  );

  const handleSelectItem = useCallback(
    (item: ComboItem) => {
      if (item.kind === "other-municipality") {
        handleSelect({ barrioId: null, otherMunicipality: true });
      } else {
        handleSelect({ barrioId: item.barrio.id, otherMunicipality: false });
      }
    },
    [handleSelect],
  );

  const handleClear = useCallback(() => {
    handleSelect({ barrioId: null, otherMunicipality: false });
  }, [handleSelect]);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (items.length === 0 ? 0 : (i + 1) % items.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (items.length === 0 ? 0 : (i - 1 + items.length) % items.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = items[clampedActive];
      if (!item) return;
      handleSelectItem(item);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  const hasSelection = value.otherMunicipality || selectedBarrio != null;
  const triggerText = value.otherMunicipality
    ? OTHER_MUNICIPALITY_LABEL
    : selectedBarrio
      ? displayLabel(selectedBarrio)
      : placeholder;

  const errorId = error ? `${reactId}-error` : undefined;

  return (
    <div className={cn("space-y-2", className)} ref={containerRef}>
      {label && (
        <label
          htmlFor={reactId}
          className="block text-sm font-medium leading-none text-charcoal"
        >
          {label}
        </label>
      )}

      <div className="relative">
        <button
          ref={triggerRef}
          id={reactId}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-controls={listboxId}
          aria-invalid={!!error || undefined}
          aria-describedby={errorId}
          data-testid={dataTestId}
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex h-12 w-full items-center justify-between gap-2 rounded-control border border-surface-muted bg-surface-raised px-3 py-2 text-left text-sm text-charcoal transition-colors focus-visible:outline-none focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50",
            !hasSelection && "text-mid-gray",
            error && "border-danger ring-1 ring-danger/30",
          )}
        >
          <span className="min-w-0 flex-1 truncate text-left">{triggerText}</span>
          <span className="flex shrink-0 items-center gap-1">
            {hasSelection && (
              <span
                role="button"
                tabIndex={0}
                aria-label="Quitar selección"
                data-testid={`${dataTestId}-clear`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleClear();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    e.stopPropagation();
                    handleClear();
                  }
                }}
                className="rounded p-0.5 text-mid-gray hover:text-charcoal focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              >
                <X size={14} aria-hidden="true" />
              </span>
            )}
            <ChevronsUpDown size={14} className="text-mid-gray" aria-hidden="true" />
          </span>
        </button>

        {open && (
          <div
            className="absolute left-0 right-0 top-full z-50 mt-1.5 min-w-[260px] rounded-lg bg-surface-raised p-1 shadow-lg ring-1 ring-light-gray"
            data-testid={`${dataTestId}-popover`}
          >
            <div className="flex items-center gap-2 border-b border-light-gray px-2 py-2">
              <Search size={14} className="text-mid-gray" aria-hidden="true" />
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setActiveIndex(0);
                }}
                onKeyDown={handleKeyDown}
                placeholder="Buscar barrio..."
                aria-label="Buscar barrio"
                aria-controls={listboxId}
                aria-activedescendant={
                  items.length > 0 ? `${reactId}-opt-${clampedActive}` : undefined
                }
                data-testid={`${dataTestId}-search`}
                className="w-full bg-transparent text-sm text-charcoal placeholder:text-mid-gray outline-none"
              />
            </div>

            <ul
              id={listboxId}
              role="listbox"
              aria-label={label ?? "Barrios"}
              className="max-h-72 overflow-y-auto py-1"
            >
              {barriosQuery.isLoading && (
                <li className="space-y-1 p-2" aria-hidden="true">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-8 animate-pulse rounded-md bg-light-gray"
                      data-testid={`${dataTestId}-skeleton`}
                    />
                  ))}
                </li>
              )}

              {barriosQuery.isError && (
                <li
                  role="alert"
                  className="flex items-start gap-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700"
                  data-testid={`${dataTestId}-error-state`}
                >
                  <AlertCircle size={14} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span>No se pudo cargar el catálogo de barrios. Reintenta más tarde.</span>
                </li>
              )}

              {!barriosQuery.isLoading && !barriosQuery.isError && items.length === 0 && (
                <li
                  className="px-3 py-4 text-center text-xs text-mid-gray"
                  data-testid={`${dataTestId}-empty`}
                >
                  Sin barrios que coincidan.
                </li>
              )}

              {!barriosQuery.isLoading &&
                !barriosQuery.isError &&
                items.map((item, idx) => {
                  const optId = `${reactId}-opt-${idx}`;
                  const isActive = idx === clampedActive;

                  if (item.kind === "other-municipality") {
                    const isSelected = value.otherMunicipality;
                    return (
                      <li
                        key="other-municipality"
                        id={optId}
                        role="option"
                        aria-selected={isSelected}
                        data-testid={`${dataTestId}-option-other`}
                        onMouseEnter={() => setActiveIndex(idx)}
                        onClick={() => handleSelectItem(item)}
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-charcoal",
                          isActive && "bg-light-gray",
                        )}
                      >
                        <span className="flex-1 italic">{OTHER_MUNICIPALITY_LABEL}</span>
                        {isSelected && (
                          <Check size={14} className="text-charcoal" aria-hidden="true" />
                        )}
                      </li>
                    );
                  }

                  const barrio = item.barrio;
                  const isSelected = !value.otherMunicipality && value.barrioId === barrio.id;
                  return (
                    <li
                      key={barrio.id}
                      id={optId}
                      role="option"
                      aria-selected={isSelected}
                      data-testid={`${dataTestId}-option-${barrio.id}`}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => handleSelectItem(item)}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-charcoal",
                        isActive && "bg-light-gray",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {barrio.name}
                        <span className="ml-2 text-xs text-mid-gray">
                          {zoneLabel(barrio.zone)}
                        </span>
                      </span>
                      {isSelected && (
                        <Check size={14} className="text-charcoal" aria-hidden="true" />
                      )}
                    </li>
                  );
                })}
            </ul>
          </div>
        )}
      </div>

      {error && (
        <p id={errorId} role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
