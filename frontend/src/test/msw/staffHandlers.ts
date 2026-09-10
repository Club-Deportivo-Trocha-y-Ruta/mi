/**
 * MSW handlers del personal del club (feature 041 — gobernanza multi-coach,
 * US3). Contrato: specs/041-multi-coach-governance/contracts/staff-admin.md
 * §1, §3, §4.
 *
 * Cubre:
 *   - GET /api/users (role=coach&role=admin)
 *   - POST /api/users
 *   - PATCH /api/users/:id
 *   - GET /api/clubs/
 *
 * Nombres inventados de personas adultas únicamente — ningún menor aparece
 * en estos fixtures.
 */
import { http, HttpResponse } from "msw";

import type { ClubOut, UserListOut, UserOut } from "@/types/user.types";
import { UserRole } from "@/types/enums";

export function makeStaffUser(overrides?: Partial<UserOut>): UserOut {
  return {
    id: 3,
    email: "laura.mendez@example.org",
    first_name: "Laura",
    last_name: "Méndez",
    phone: null,
    role: UserRole.coach,
    is_active: true,
    can_login: true,
    created_at: "2026-02-01T09:12:44",
    created_by_display_name: null,
    ...overrides,
  };
}

export function makeStaffListOut(overrides?: Partial<UserListOut>): UserListOut {
  const items = overrides?.items ?? [
    makeStaffUser(),
    makeStaffUser({
      id: 12,
      email: "ana.rivera@example.org",
      first_name: "Ana",
      last_name: "Rivera",
      phone: "3001234567",
      is_active: false,
      created_at: "2026-09-09T14:03:11",
      created_by_display_name: "Laura Méndez",
    }),
  ];
  return { items, total: overrides?.total ?? items.length };
}

export function makeClub(overrides?: Partial<ClubOut>): ClubOut {
  return {
    id: 1,
    name: "Trocha y Ruta",
    code: "TYR",
    location: "Valle del Cauca",
    is_active: true,
    created_at: "2024-01-01T00:00:00",
    ...overrides,
  };
}

export const listStaffHandler = http.get("*/api/users", ({ request }) => {
  const url = new URL(request.url);
  const roles = url.searchParams.getAll("role");
  if (roles.length > 0 && !roles.includes("coach") && !roles.includes("admin")) {
    return HttpResponse.json({ items: [], total: 0 });
  }
  return HttpResponse.json(makeStaffListOut());
});

export const createStaffHandler = http.post("*/api/users", async ({ request }) => {
  const body = (await request.json()) as Record<string, unknown>;
  return HttpResponse.json(
    makeStaffUser({
      id: 99,
      first_name: String(body.first_name ?? ""),
      last_name: String(body.last_name ?? ""),
      email: String(body.email ?? ""),
      phone: (body.phone as string | null) ?? null,
      role: (body.role as UserRole) ?? UserRole.coach,
      created_by_display_name: "Laura Méndez",
    }),
    { status: 201 },
  );
});

export const setStaffActiveHandler = http.patch(
  "*/api/users/:id",
  async ({ request, params }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      makeStaffUser({
        id: Number(params.id),
        is_active: Boolean(body.is_active),
      }),
    );
  },
);

export const listClubsHandler = http.get("*/api/clubs/", () =>
  HttpResponse.json([makeClub()]),
);

export const staffHandlers = [
  listStaffHandler,
  createStaffHandler,
  setStaffActiveHandler,
  listClubsHandler,
];
