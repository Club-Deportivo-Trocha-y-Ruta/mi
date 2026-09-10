/**
 * StaffPage — "Personal del club" (feature 041 — gobernanza multi-coach,
 * US3). Ruta `/admin/usuarios`, admin-only. Contrato:
 * specs/041-multi-coach-governance/contracts/staff-admin.md §6, §8.
 */
import * as React from "react";
import { Plus } from "lucide-react";

import { StaffCreateSheet } from "@/components/admin/StaffCreateSheet";
import { StaffStateDialog } from "@/components/admin/StaffStateDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useStaff } from "@/hooks/admin/useStaff";
import { useSetStaffActive } from "@/hooks/admin/useSetStaffActive";
import { useAuthStore } from "@/store/auth.store";
import { extractErrorDetail } from "@/lib/apiError";
import { formatDateMedium } from "@/lib/datetime";
import type { UserOut } from "@/types/user.types";

type StateFilter = "all" | "active" | "inactive";

function toIsActive(filter: StateFilter): boolean | undefined {
  if (filter === "active") return true;
  if (filter === "inactive") return false;
  return undefined;
}

export function StaffPage() {
  const currentUserId = useAuthStore((s) => s.user?.id);
  const [stateFilter, setStateFilter] = React.useState<StateFilter>("all");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [stateTarget, setStateTarget] = React.useState<{
    user: UserOut;
    action: "deactivate" | "reactivate";
  } | null>(null);
  const [stateError, setStateError] = React.useState<string | null>(null);

  const staffQuery = useStaff({ isActive: toIsActive(stateFilter) });
  const setActiveMutation = useSetStaffActive();

  const items = staffQuery.data?.items ?? [];
  const total = staffQuery.data?.total ?? 0;

  function handleStateConfirm(reasonCode: string) {
    if (!stateTarget) return;
    setStateError(null);
    setActiveMutation.mutate(
      {
        id: stateTarget.user.id,
        body: {
          is_active: stateTarget.action === "reactivate",
          reason_code: reasonCode,
        },
      },
      {
        onSuccess: () => {
          setStateTarget(null);
        },
        onError: (err) => {
          setStateError(
            extractErrorDetail(
              err,
              "No se pudo actualizar el estado de la cuenta. Intenta de nuevo.",
            ),
          );
        },
      },
    );
  }

  return (
    <section className="space-y-5" data-testid="staff-page">
      <PageHeader
        title="Personal del club"
        subtitle="Entrenadores y administradores con acceso al club."
        actions={
          <Button
            type="button"
            className="min-h-12"
            data-testid="staff-new-button"
            onClick={() => setCreateOpen(true)}
          >
            <Plus size={16} className="mr-1.5" aria-hidden="true" />
            Nuevo entrenador
          </Button>
        }
      />

      <div className="flex items-center gap-2">
        <label htmlFor="staff-state-filter" className="text-xs font-medium text-mid-gray">
          Estado
        </label>
        <Select
          value={stateFilter}
          onValueChange={(value) => setStateFilter(value as StateFilter)}
        >
          <SelectTrigger
            id="staff-state-filter"
            data-testid="staff-state-filter"
            className="min-h-12 w-40"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            <SelectItem value="active">Activos</SelectItem>
            <SelectItem value="inactive">Inactivos</SelectItem>
          </SelectContent>
        </Select>
        <span className="sr-only" role="status" aria-live="polite">
          {total} cuentas
        </span>
      </div>

      {staffQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4 shadow-card"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Cargando personal…</span>
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="h-14 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {staffQuery.isError && !staffQuery.isLoading && (
        <ErrorState
          message="No se pudo cargar el personal del club."
          onRetry={async () => {
            await staffQuery.refetch();
          }}
          isColdStart={isColdStartError(staffQuery.error)}
        />
      )}

      {!staffQuery.isLoading && !staffQuery.isError && items.length === 0 && (
        <EmptyState
          title={
            stateFilter === "all"
              ? "Aún no hay personal registrado."
              : "No hay personal con ese estado."
          }
          action={
            stateFilter === "all" ? (
              <Button
                type="button"
                className="min-h-12"
                onClick={() => setCreateOpen(true)}
              >
                <Plus size={16} className="mr-1.5" aria-hidden="true" />
                Nuevo entrenador
              </Button>
            ) : undefined
          }
        />
      )}

      {!staffQuery.isLoading && !staffQuery.isError && items.length > 0 && (
        <div className="rounded-xl bg-white shadow-card">
          <Table data-testid="staff-table">
            <caption className="sr-only">Personal del club</caption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Nombre</TableHead>
                <TableHead scope="col">Rol</TableHead>
                <TableHead scope="col">Estado</TableHead>
                <TableHead scope="col">Creado el</TableHead>
                <TableHead scope="col">Creado por</TableHead>
                <TableHead scope="col" className="text-right">
                  Acciones
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((user) => {
                const fullName = `${user.first_name} ${user.last_name}`.trim();
                const isSelf = currentUserId === user.id;
                return (
                  <TableRow key={user.id} data-testid={`staff-row-${user.id}`}>
                    <TableCell>
                      <div>{fullName}</div>
                      <div className="text-xs text-mid-gray">{user.email}</div>
                    </TableCell>
                    <TableCell>
                      {user.role === "admin" ? "Administrador" : "Entrenador"}
                    </TableCell>
                    <TableCell data-testid={`staff-row-state-${user.id}`}>
                      {user.is_active ? (
                        <StatusBadge status="success" label="Activo" />
                      ) : (
                        <StatusBadge status="neutral" label="Inactivo" />
                      )}
                    </TableCell>
                    <TableCell>{formatDateMedium(user.created_at)}</TableCell>
                    <TableCell data-testid={`staff-row-created-by-${user.id}`}>
                      {user.created_by_display_name ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {!isSelf && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="min-h-12"
                          data-testid={`staff-toggle-active-${user.id}`}
                          aria-label={`${user.is_active ? "Desactivar" : "Reactivar"} a ${fullName}`}
                          onClick={() => {
                            setStateError(null);
                            setStateTarget({
                              user,
                              action: user.is_active ? "deactivate" : "reactivate",
                            });
                          }}
                        >
                          {user.is_active ? "Desactivar" : "Reactivar"}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <StaffCreateSheet open={createOpen} onOpenChange={setCreateOpen} />

      <StaffStateDialog
        open={stateTarget !== null}
        action={stateTarget?.action ?? null}
        staffFullName={
          stateTarget
            ? `${stateTarget.user.first_name} ${stateTarget.user.last_name}`.trim()
            : ""
        }
        isPending={setActiveMutation.isPending}
        errorMessage={stateError ?? undefined}
        onCancel={() => setStateTarget(null)}
        onConfirm={handleStateConfirm}
      />
    </section>
  );
}
