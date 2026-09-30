/**
 * BarrioCatalogPage — catálogo de barrios de Yumbo, admin only (feature 047).
 * Ruta `/imderty/barrios` (registrada en T012, `ProtectedRoute allowedRoles={[admin]}`).
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md` §Barrio catalog.
 *
 * Patrón responsive (constitution III, FR-029): tabla con edición en línea
 * (nombre + zona + activar/desactivar) a ≥ 768 px, tarjetas con una hoja de
 * edición a 360 px — mismo patrón de `routes/admin/StaffPage.tsx`. Agregar
 * un barrio usa la misma hoja (`BarrioFormSheet`) en cualquier ancho, porque
 * no hay una fila existente donde insertar la edición en línea.
 *
 * El 409 de nombre duplicado (contrato) se muestra en el campo "Nombre" de
 * la hoja, y como error en línea en la fila que se estaba editando en la
 * tabla — nunca como toast genérico, para que quede junto al dato que causó
 * el conflicto.
 */
import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, MapPin, Pencil, Plus } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";

import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableScrollContainer,
} from "@/components/ui/table";
import { useBarrios, useCreateBarrio, useUpdateBarrio } from "@/hooks/useImderty";
import { extractErrorDetail } from "@/lib/apiError";
import {
  barrioCreateSchema,
  imdertyBarrioZones,
  type Barrio,
  type ImdertyBarrioZone,
} from "@/schemas/imderty";

const DUPLICATE_NAME_MESSAGE = "Ya existe un barrio con ese nombre.";

/** "1"–"4" → "Comuna 1"; "ZONA NORTE" → "Zona Norte" (contrato/data-model). */
function zoneLabel(zone: string): string {
  if (/^[1-4]$/.test(zone)) return `Comuna ${zone}`;
  return zone
    .toLowerCase()
    .split(" ")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function isDuplicateNameError(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 409;
}

type StateFilter = "all" | "active" | "inactive";

type BarrioFormValues = z.input<typeof barrioCreateSchema>;

const zoneOptions = imdertyBarrioZones.map((zone) => ({ value: zone, label: zoneLabel(zone) }));

// ---------------------------------------------------------------------------
// Hoja de alta / edición — reutilizada por "Agregar barrio" (cualquier
// ancho) y por "Editar" en las tarjetas móviles (< 768 px).
// ---------------------------------------------------------------------------

interface BarrioFormSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  barrio: Barrio | null; // null = alta
}

function BarrioFormSheet({ open, onOpenChange, barrio }: BarrioFormSheetProps) {
  const isEdit = barrio !== null;
  const createMutation = useCreateBarrio();
  const updateMutation = useUpdateBarrio();
  const mutation = isEdit ? updateMutation : createMutation;

  const form = useForm<BarrioFormValues>({
    resolver: zodResolver(barrioCreateSchema),
    defaultValues: { name: "", zone: "1", is_active: true },
  });

  React.useEffect(() => {
    if (!open) return;
    form.reset({
      name: barrio?.name ?? "",
      zone: (barrio?.zone as ImdertyBarrioZone) ?? "1",
      is_active: barrio?.is_active ?? true,
    });
    createMutation.reset();
    updateMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, barrio]);

  function handleSubmit(values: BarrioFormValues) {
    const payload = {
      name: values.name.trim(),
      zone: values.zone,
      is_active: values.is_active ?? true,
    };
    const onError = (err: unknown) => {
      if (isDuplicateNameError(err)) {
        form.setError("name", { message: DUPLICATE_NAME_MESSAGE });
        return;
      }
      form.setError("root", {
        message: extractErrorDetail(err, "No se pudo guardar el barrio. Intenta de nuevo."),
      });
    };
    if (isEdit) {
      updateMutation.mutate(
        { barrioId: barrio.id, payload },
        { onSuccess: () => onOpenChange(false), onError },
      );
    } else {
      createMutation.mutate(payload, { onSuccess: () => onOpenChange(false), onError });
    }
  }

  const isPending = mutation.isPending;
  const rootError = form.formState.errors.root?.message;

  return (
    <Sheet open={open} onOpenChange={(next) => !isPending && onOpenChange(next)}>
      <SheetContent data-testid="barrio-form-sheet" side="right">
        <form className="flex h-full flex-col" onSubmit={form.handleSubmit(handleSubmit)} noValidate>
          <SheetHeader>
            <SheetTitle>{isEdit ? "Editar barrio" : "Agregar barrio"}</SheetTitle>
            <SheetDescription>
              {isEdit
                ? "Cambia el nombre, la comuna/zona o el estado de este barrio."
                : "Se agrega al catálogo de barrios de Yumbo usado por la planilla IMDERTY."}
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="barrio-name" className="text-xs font-medium text-mid-gray">
                Nombre
              </label>
              <Input
                id="barrio-name"
                autoComplete="off"
                aria-invalid={!!form.formState.errors.name}
                {...form.register("name")}
              />
              {form.formState.errors.name && (
                <p role="alert" className="text-sm text-danger">
                  {form.formState.errors.name.message}
                </p>
              )}
            </div>

            <div className="space-y-1">
              <label htmlFor="barrio-zone" className="text-xs font-medium text-mid-gray">
                Comuna / zona
              </label>
              <Controller
                control={form.control}
                name="zone"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="barrio-zone" data-testid="barrio-zone-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {zoneOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border border-hairline px-3 py-2.5">
              <div>
                <p className="text-sm font-medium text-charcoal">Barrio activo</p>
                <p className="text-xs text-mid-gray">
                  Los barrios inactivos no aparecen para elegir en el perfil del atleta.
                </p>
              </div>
              <Controller
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    aria-label="Barrio activo"
                    data-testid="barrio-active-switch"
                  />
                )}
              />
            </div>

            {rootError && (
              <p role="alert" className="text-sm text-danger">
                {rootError}
              </p>
            )}
          </SheetBody>

          <SheetFooter>
            <Button
              type="button"
              variant="outline"
              className="min-h-12"
              disabled={isPending}
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              className="min-h-12"
              disabled={isPending}
              data-testid="barrio-form-submit"
            >
              {isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {isEdit ? "Guardar cambios" : "Agregar barrio"}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

function toStateFilterPredicate(filter: StateFilter): (barrio: Barrio) => boolean {
  if (filter === "active") return (barrio) => barrio.is_active;
  if (filter === "inactive") return (barrio) => !barrio.is_active;
  return () => true;
}

export function BarrioCatalogPage() {
  const [stateFilter, setStateFilter] = React.useState<StateFilter>("all");
  const [formTarget, setFormTarget] = React.useState<{ open: boolean; barrio: Barrio | null }>({
    open: false,
    barrio: null,
  });

  // Desktop: edición en línea de una sola fila a la vez.
  const [editingId, setEditingId] = React.useState<number | null>(null);
  const [editName, setEditName] = React.useState("");
  const [editZone, setEditZone] = React.useState<ImdertyBarrioZone>("1");
  const [editError, setEditError] = React.useState<string | null>(null);

  const barriosQuery = useBarrios(true);
  const updateMutation = useUpdateBarrio();

  const items = barriosQuery.data ?? [];
  const filtered = items.filter(toStateFilterPredicate(stateFilter));

  function startEdit(barrio: Barrio) {
    setEditingId(barrio.id);
    setEditName(barrio.name);
    setEditZone(barrio.zone);
    setEditError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditError(null);
    updateMutation.reset();
  }

  function saveEdit(barrioId: number) {
    const trimmed = editName.trim();
    if (!trimmed) {
      setEditError("Ingresa el nombre del barrio");
      return;
    }
    setEditError(null);
    updateMutation.mutate(
      { barrioId, payload: { name: trimmed, zone: editZone } },
      {
        onSuccess: () => {
          setEditingId(null);
        },
        onError: (err) => {
          setEditError(
            isDuplicateNameError(err)
              ? DUPLICATE_NAME_MESSAGE
              : extractErrorDetail(err, "No se pudo guardar el cambio. Intenta de nuevo."),
          );
        },
      },
    );
  }

  function toggleActive(barrio: Barrio) {
    setEditError(null);
    updateMutation.mutate({ barrioId: barrio.id, payload: { is_active: !barrio.is_active } });
  }

  const isRowPending = (barrioId: number) =>
    updateMutation.isPending && updateMutation.variables?.barrioId === barrioId;

  return (
    <section className="space-y-5" data-testid="barrio-catalog-page">
      <PageHeader
        title="Catálogo de barrios"
        subtitle="Barrios de Yumbo y su comuna o zona, usados por la planilla IMDERTY."
        actions={
          <Button
            type="button"
            className="min-h-12"
            data-testid="barrio-add-button"
            onClick={() => setFormTarget({ open: true, barrio: null })}
          >
            <Plus size={16} className="mr-1.5" aria-hidden="true" />
            Agregar barrio
          </Button>
        }
      />

      <div className="flex items-center gap-2">
        <label htmlFor="barrio-state-filter" className="text-xs font-medium text-mid-gray">
          Estado
        </label>
        <Select value={stateFilter} onValueChange={(value) => setStateFilter(value as StateFilter)}>
          <SelectTrigger id="barrio-state-filter" data-testid="barrio-state-filter" className="min-h-12 w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            <SelectItem value="active">Activos</SelectItem>
            <SelectItem value="inactive">Inactivos</SelectItem>
          </SelectContent>
        </Select>
        <span className="sr-only" role="status" aria-live="polite">
          {filtered.length} barrios
        </span>
      </div>

      {barriosQuery.isLoading && (
        <div
          className="space-y-2 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Cargando catálogo de barrios…</span>
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={idx} className="h-14 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {barriosQuery.isError && !barriosQuery.isLoading && (
        <ErrorState
          message="No se pudo cargar el catálogo de barrios."
          onRetry={async () => {
            await barriosQuery.refetch();
          }}
          isColdStart={isColdStartError(barriosQuery.error)}
        />
      )}

      {!barriosQuery.isLoading && !barriosQuery.isError && filtered.length === 0 && (
        <EmptyState
          icon={MapPin}
          title={
            stateFilter === "all"
              ? "Aún no hay barrios en el catálogo."
              : "No hay barrios con ese estado."
          }
          action={
            stateFilter === "all" ? (
              <Button
                type="button"
                className="min-h-12"
                onClick={() => setFormTarget({ open: true, barrio: null })}
              >
                <Plus size={16} className="mr-1.5" aria-hidden="true" />
                Agregar barrio
              </Button>
            ) : undefined
          }
        />
      )}

      {!barriosQuery.isLoading && !barriosQuery.isError && filtered.length > 0 && (
        <>
          {/* Tarjetas móvil (<md) — edición en una hoja, patrón de StaffPage. */}
          <ul role="list" className="flex flex-col gap-3 md:hidden">
            {filtered.map((barrio) => (
              <li key={barrio.id}>
                <div
                  className="rounded-card bg-surface-raised p-4 space-y-2 shadow-card ring-1 ring-hairline"
                  data-testid={`barrio-row-${barrio.id}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-charcoal">{barrio.name}</p>
                      <p className="truncate text-xs text-mid-gray">{zoneLabel(barrio.zone)}</p>
                    </div>
                    <span data-testid={`barrio-row-state-${barrio.id}`}>
                      {barrio.is_active ? (
                        <StatusBadge status="success" label="Activo" />
                      ) : (
                        <StatusBadge status="neutral" label="Inactivo" />
                      )}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-h-12 w-full"
                    data-testid={`barrio-edit-${barrio.id}`}
                    aria-label={`Editar ${barrio.name}`}
                    onClick={() => setFormTarget({ open: true, barrio })}
                  >
                    <Pencil size={14} className="mr-1.5" aria-hidden="true" />
                    Editar
                  </Button>
                </div>
              </li>
            ))}
          </ul>

          {/* Tabla desktop (≥ md) — edición en línea por fila. */}
          <div className="hidden rounded-card bg-surface-raised shadow-card ring-1 ring-hairline md:block">
            <TableScrollContainer className="rounded-xl">
              <Table data-testid="barrio-table">
                <caption className="sr-only">Catálogo de barrios</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Nombre</TableHead>
                    <TableHead scope="col">Comuna / zona</TableHead>
                    <TableHead scope="col">Estado</TableHead>
                    <TableHead scope="col" className="sticky right-0 z-10 bg-surface-raised text-right">
                      Acciones
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((barrio) => {
                    const isEditingRow = editingId === barrio.id;
                    const pending = isRowPending(barrio.id);
                    return (
                      <TableRow key={barrio.id} className="group" data-testid={`barrio-row-${barrio.id}`}>
                        <TableCell>
                          {isEditingRow ? (
                            <>
                              <Input
                                aria-label="Nombre del barrio"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                data-testid={`barrio-edit-name-${barrio.id}`}
                                className="min-h-10"
                              />
                              {editError && (
                                <p role="alert" className="mt-1 text-xs text-danger">
                                  {editError}
                                </p>
                              )}
                            </>
                          ) : (
                            barrio.name
                          )}
                        </TableCell>
                        <TableCell>
                          {isEditingRow ? (
                            <Select
                              value={editZone}
                              onValueChange={(value) => setEditZone(value as ImdertyBarrioZone)}
                            >
                              <SelectTrigger
                                aria-label="Comuna o zona"
                                data-testid={`barrio-edit-zone-${barrio.id}`}
                                className="min-h-10"
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {zoneOptions.map((option) => (
                                  <SelectItem key={option.value} value={option.value}>
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          ) : (
                            zoneLabel(barrio.zone)
                          )}
                        </TableCell>
                        <TableCell data-testid={`barrio-row-state-${barrio.id}`}>
                          {barrio.is_active ? (
                            <StatusBadge status="success" label="Activo" />
                          ) : (
                            <StatusBadge status="neutral" label="Inactivo" />
                          )}
                        </TableCell>
                        <TableCell className="sticky right-0 bg-surface-raised text-right group-hover:bg-light-gray/50">
                          {isEditingRow ? (
                            <div className="flex justify-end gap-2">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="min-h-10"
                                disabled={pending}
                                onClick={cancelEdit}
                              >
                                Cancelar
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                className="min-h-10"
                                disabled={pending}
                                data-testid={`barrio-save-${barrio.id}`}
                                onClick={() => saveEdit(barrio.id)}
                              >
                                {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                                Guardar
                              </Button>
                            </div>
                          ) : (
                            <div className="flex justify-end gap-2">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="min-h-10"
                                data-testid={`barrio-edit-${barrio.id}`}
                                aria-label={`Editar ${barrio.name}`}
                                onClick={() => startEdit(barrio)}
                              >
                                <Pencil size={14} aria-hidden="true" />
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="min-h-10"
                                disabled={pending}
                                data-testid={`barrio-toggle-active-${barrio.id}`}
                                aria-label={`${barrio.is_active ? "Desactivar" : "Activar"} ${barrio.name}`}
                                onClick={() => toggleActive(barrio)}
                              >
                                {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                                {barrio.is_active ? "Desactivar" : "Activar"}
                              </Button>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableScrollContainer>
          </div>
        </>
      )}

      <BarrioFormSheet
        open={formTarget.open}
        barrio={formTarget.barrio}
        onOpenChange={(open) => setFormTarget((prev) => ({ ...prev, open }))}
      />
    </section>
  );
}

export default BarrioCatalogPage;
