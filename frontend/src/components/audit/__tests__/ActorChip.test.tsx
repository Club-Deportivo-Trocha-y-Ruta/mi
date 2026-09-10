/**
 * Tests de ActorChip (feature 041 — gobernanza multi-coach, T085).
 * Contrato: specs/041-multi-coach-governance/contracts/coach-activity-report.md §7.2.
 *
 * `useStaff` se mockea (mismo patrón de `StaffPage.test.tsx`) para controlar
 * de forma determinista los tres estados del directorio: cargando,
 * resuelto, y "no aparece".
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { UserRole } from "@/types/enums";
import type { UserOut } from "@/types/user.types";

const useStaffMock = vi.fn();
vi.mock("@/hooks/admin/useStaff", () => ({
  useStaff: () => useStaffMock(),
}));

import { ActorChip } from "@/components/audit/ActorChip";

function makeStaffUser(overrides?: Partial<UserOut>): UserOut {
  return {
    id: 7,
    email: "ana.coach@example.org",
    first_name: "Ana",
    last_name: "Coach",
    phone: null,
    role: UserRole.coach,
    is_active: true,
    can_login: true,
    created_at: "2026-01-01T00:00:00",
    created_by_display_name: null,
    ...overrides,
  };
}

describe("ActorChip", () => {
  beforeEach(() => {
    useStaffMock.mockClear();
  });

  it("usa el nombre ya resuelto cuando llega displayName", () => {
    useStaffMock.mockReturnValue({ data: undefined, isLoading: false });
    render(<ActorChip userId={7} displayName="Ana Coach" />);

    expect(screen.getByText("Ana Coach")).toBeInTheDocument();
    // No debe consultar el directorio si ya tiene el nombre.
    expect(useStaffMock).not.toHaveBeenCalled();
  });

  it("muestra la insignia 'Inactivo' cuando displayName viene con isActive=false", () => {
    useStaffMock.mockReturnValue({ data: undefined, isLoading: false });
    render(<ActorChip userId={12} displayName="Bruno Coach" isActive={false} />);

    expect(screen.getByText("Bruno Coach")).toBeInTheDocument();
    expect(screen.getByText("Inactivo")).toBeInTheDocument();
  });

  it("resuelve el nombre desde el directorio cuando solo hay userId", () => {
    useStaffMock.mockReturnValue({
      data: { items: [makeStaffUser()], total: 1 },
      isLoading: false,
    });
    render(<ActorChip userId={7} />);

    expect(screen.getByText("Ana Coach")).toBeInTheDocument();
  });

  it("muestra 'Inactivo' cuando el directorio resuelve una cuenta desactivada", () => {
    useStaffMock.mockReturnValue({
      data: { items: [makeStaffUser({ is_active: false })], total: 1 },
      isLoading: false,
    });
    render(<ActorChip userId={7} />);

    expect(screen.getByText("Ana Coach")).toBeInTheDocument();
    expect(screen.getByText("Inactivo")).toBeInTheDocument();
  });

  it("muestra un Skeleton mientras el directorio está cargando, nunca el id crudo", () => {
    useStaffMock.mockReturnValue({ data: undefined, isLoading: true });
    render(<ActorChip userId={7} />);

    expect(screen.getByTestId("actor-chip-skeleton")).toBeInTheDocument();
    expect(screen.queryByText("7")).not.toBeInTheDocument();
  });

  it("muestra 'Usuario no disponible' cuando el id no aparece en el directorio", () => {
    useStaffMock.mockReturnValue({
      data: { items: [makeStaffUser({ id: 99 })], total: 1 },
      isLoading: false,
    });
    render(<ActorChip userId={7} />);

    expect(screen.getByText("Usuario no disponible")).toBeInTheDocument();
  });

  it("muestra 'Proceso automático' cuando actorKind no es 'user'", () => {
    useStaffMock.mockReturnValue({ data: undefined, isLoading: false });
    render(<ActorChip userId={null} actorKind="system" />);

    expect(screen.getByText("Proceso automático")).toBeInTheDocument();
    expect(useStaffMock).not.toHaveBeenCalled();
  });

  it("muestra 'Proceso automático' cuando userId es null sin actorKind", () => {
    useStaffMock.mockReturnValue({ data: undefined, isLoading: false });
    render(<ActorChip userId={null} />);

    expect(screen.getByText("Proceso automático")).toBeInTheDocument();
  });

  it("nunca renderiza el id numérico crudo del actor", () => {
    useStaffMock.mockReturnValue({
      data: { items: [makeStaffUser({ id: 456 })], total: 1 },
      isLoading: false,
    });
    render(<ActorChip userId={456} />);

    expect(screen.queryByText("456")).not.toBeInTheDocument();
  });
});
