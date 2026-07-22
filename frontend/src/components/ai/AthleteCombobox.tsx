/**
 * AthleteCombobox — selector accesible de atletas del club del coach.
 *
 * Reemplaza el input numérico "Athlete ID" del StartRunForm y se usa también
 * como filtro de contexto del chat. El coach jamás debería tener que conocer
 * el ID numérico de un deportista.
 *
 * Implementación: dropdown casero (button + div posicionado) sin Radix
 * Popover ni cmdk — para evitar duplicación de Radix Popover en el chunk
 * lazy `RaceAnalysisPage-*.js`. Mantenemos las garantías de accesibilidad
 * manualmente (role=combobox, listbox, aria-activedescendant, soporte
 * teclado, focus trap mínimo, click-outside).
 *
 * Características:
 *  - Búsqueda case-insensitive y diacritic-insensitive (quita acentos).
 *  - Teclado: ArrowUp/Down navegan, Enter selecciona, Esc cierra.
 *  - role=combobox + aria-expanded + aria-controls + aria-activedescendant.
 *  - Estados: loading skeleton, lista vacía, error con Alert.
 *  - El value externo es siempre el `athlete.id` (number) — el backend sigue
 *    recibiendo el id numérico, sólo la UX cambia.
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

import { useAthletes } from "@/hooks/athletes/useAthletes";
import { cn } from "@/lib/utils";
import type { AthleteOut } from "@/types/athlete.types";

interface AthleteComboboxProps {
  /** Atleta seleccionado (id numérico). `null` = sin selección. */
  value: number | null;
  /** Callback con el nuevo id (o `null` si se limpia). */
  onChange: (id: number | null) => void;
  /** Texto cuando no hay nada seleccionado. */
  placeholder?: string;
  /** Etiqueta accesible — siempre renderizada como label asociado al combobox. */
  label?: string;
  /** Mensaje de error de validación (forma). */
  error?: string;
  /** Si se permite incluir opción "Cualquier deportista" (sin filtro). */
  allowAny?: boolean;
  /** Texto del item "any" cuando allowAny=true. */
  anyLabel?: string;
  /** id del input (para asociar labels externos). */
  id?: string;
  className?: string;
  /** Para testids/aria-describedby externos. */
  "data-testid"?: string;
}

/** Normaliza string para comparar sin acentos ni mayúsculas. */
function normalize(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

function initialsOf(athlete: AthleteOut): string {
  const f = athlete.first_name?.[0] ?? "";
  const l = athlete.last_name?.[0] ?? "";
  return `${f}${l}`.toUpperCase() || "?";
}

function displayLabel(athlete: AthleteOut): string {
  const name = `${athlete.first_name} ${athlete.last_name}`.trim();
  return athlete.category ? `${name} · ${athlete.category}` : name;
}

export function AthleteCombobox({
  value,
  onChange,
  placeholder = "Selecciona un deportista",
  label,
  error,
  allowAny = false,
  anyLabel = "Cualquier deportista",
  id,
  className,
  "data-testid": dataTestId = "athlete-combobox",
}: AthleteComboboxProps) {
  const reactId = useMemo(
    () => id ?? `athlete-combobox-${Math.random().toString(36).slice(2, 8)}`,
    [id],
  );
  const listboxId = `${reactId}-listbox`;

  const athletesQuery = useAthletes();
  const athletes = athletesQuery.data?.items ?? [];

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
      // Microtask para esperar al render del panel.
      const t = setTimeout(
        () => inputRef.current?.focus({ preventScroll: true }),
        10,
      );
      return () => clearTimeout(t);
    }
  }, [open]);

  const selected = useMemo<AthleteOut | null>(() => {
    if (value == null) return null;
    return athletes.find((a) => a.id === value) ?? null;
  }, [value, athletes]);

  const filtered = useMemo(() => {
    const q = normalize(search);
    if (!q) return athletes;
    return athletes.filter((a) => {
      const hay = normalize(
        `${a.first_name} ${a.last_name} ${a.category ?? ""}`,
      );
      return hay.includes(q);
    });
  }, [athletes, search]);

  // Items mostrados — incluye el item "any" cuando aplica y no hay búsqueda.
  const items = useMemo(() => {
    if (allowAny && !search.trim()) {
      return [
        { kind: "any" as const },
        ...filtered.map((a) => ({ kind: "athlete" as const, athlete: a })),
      ];
    }
    return filtered.map((a) => ({ kind: "athlete" as const, athlete: a }));
  }, [allowAny, search, filtered]);

  const clampedActive =
    items.length === 0 ? 0 : Math.min(activeIndex, items.length - 1);

  const handleSelect = useCallback(
    (newId: number | null) => {
      onChange(newId);
      setOpen(false);
      // Devolvemos foco al trigger por accesibilidad.
      setTimeout(() => triggerRef.current?.focus(), 0);
    },
    [onChange],
  );

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
      if (item.kind === "any") handleSelect(null);
      else handleSelect(item.athlete.id);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  const triggerText = selected
    ? displayLabel(selected)
    : value != null && !athletesQuery.isLoading
      ? `Deportista #${value}`
      : placeholder;

  const errorId = error ? `${reactId}-error` : undefined;

  return (
    <div className={cn("space-y-1", className)} ref={containerRef}>
      {label && (
        <label
          htmlFor={reactId}
          className="block text-xs font-medium text-mid-gray"
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
            "flex w-full items-center justify-between gap-2 rounded-lg bg-white px-3 py-2 text-left text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50",
            !selected && "text-mid-gray",
            !error && "shadow-ring",
          )}
          style={
            error
              ? { boxShadow: "rgb(220, 38, 38) 0px 0px 0px 1px" }
              : undefined
          }
        >
          <span className="flex min-w-0 flex-1 items-center gap-2">
            {selected && (
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-light-gray text-[10px] font-semibold text-charcoal"
              >
                {initialsOf(selected)}
              </span>
            )}
            <span className="truncate">{triggerText}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1">
            {selected && (
              <span
                role="button"
                tabIndex={0}
                aria-label="Quitar selección"
                data-testid={`${dataTestId}-clear`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleSelect(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    e.stopPropagation();
                    handleSelect(null);
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
            className="absolute left-0 right-0 top-full z-50 mt-1.5 min-w-[260px] rounded-lg bg-white p-1 shadow-lg ring-1 ring-light-gray"
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
                placeholder="Buscar por nombre o categoría..."
                aria-label="Buscar deportista"
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
              aria-label={label ?? "Deportistas"}
              className="max-h-72 overflow-y-auto py-1"
            >
              {athletesQuery.isLoading && (
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

              {athletesQuery.isError && (
                <li
                  role="alert"
                  className="flex items-start gap-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700"
                  data-testid={`${dataTestId}-error-state`}
                >
                  <AlertCircle size={14} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span>No se pudo cargar el listado de deportistas. Reintenta más tarde.</span>
                </li>
              )}

              {!athletesQuery.isLoading && !athletesQuery.isError && items.length === 0 && (
                <li
                  className="px-3 py-4 text-center text-xs text-mid-gray"
                  data-testid={`${dataTestId}-empty`}
                >
                  Sin atletas que coincidan.
                </li>
              )}

              {!athletesQuery.isLoading &&
                !athletesQuery.isError &&
                items.map((it, idx) => {
                  const optId = `${reactId}-opt-${idx}`;
                  const isActive = idx === clampedActive;
                  if (it.kind === "any") {
                    const isSelected = value == null;
                    return (
                      <li
                        key="any"
                        id={optId}
                        role="option"
                        aria-selected={isSelected}
                        data-testid={`${dataTestId}-option-any`}
                        onMouseEnter={() => setActiveIndex(idx)}
                        onClick={() => handleSelect(null)}
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-charcoal",
                          isActive && "bg-light-gray",
                        )}
                      >
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-light-gray/60 text-[10px] font-semibold text-mid-gray">
                          ✦
                        </span>
                        <span className="flex-1 italic">{anyLabel}</span>
                        {isSelected && (
                          <Check size={14} className="text-charcoal" aria-hidden="true" />
                        )}
                      </li>
                    );
                  }
                  const athlete = it.athlete;
                  const isSelected = value === athlete.id;
                  return (
                    <li
                      key={athlete.id}
                      id={optId}
                      role="option"
                      aria-selected={isSelected}
                      data-testid={`${dataTestId}-option-${athlete.id}`}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => handleSelect(athlete.id)}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-charcoal",
                        isActive && "bg-light-gray",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-light-gray text-[10px] font-semibold text-charcoal"
                      >
                        {initialsOf(athlete)}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {athlete.first_name} {athlete.last_name}
                        {athlete.category && (
                          <span className="ml-2 text-xs text-mid-gray">
                            {athlete.category}
                          </span>
                        )}
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
