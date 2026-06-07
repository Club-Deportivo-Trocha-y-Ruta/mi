/**
 * MSW handlers for the Profile & Account Settings module (spec 004-user-profile).
 *
 * Privacy: no password, token_hash, or raw token in any response.
 */
import { http, HttpResponse } from "msw";

import type { ProfileMessage, ProfileOut } from "@/types/profile.types";
import { UserRole } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixture factory
// ---------------------------------------------------------------------------

export function makeProfile(overrides?: Partial<ProfileOut>): ProfileOut {
  return {
    id: 1,
    email: "coach@trochyruta.com",
    first_name: "Carlos",
    last_name: "García",
    phone: "+57 300 000 0000",
    role: UserRole.coach,
    ...overrides,
  };
}

function profileMessage(message: string): ProfileMessage {
  return { message };
}

// ---------------------------------------------------------------------------
// Default happy-path handlers
// ---------------------------------------------------------------------------

export const profileHandlers = [
  // GET /api/profile/me
  http.get("*/api/profile/me", () => {
    return HttpResponse.json(makeProfile());
  }),

  // PATCH /api/profile/basic
  http.patch("*/api/profile/basic", async ({ request }) => {
    const body = (await request.json()) as Partial<ProfileOut>;
    return HttpResponse.json(
      makeProfile({
        first_name: body.first_name ?? "Carlos",
        last_name: body.last_name ?? "García",
        phone:
          body.phone !== undefined ? (body.phone as string | null) : "+57 300 000 0000",
      }),
    );
  }),

  // POST /api/profile/change-password
  http.post("*/api/profile/change-password", () => {
    return HttpResponse.json(
      profileMessage("Tu contraseña fue actualizada."),
    );
  }),

  // POST /api/profile/change-email/request
  http.post("*/api/profile/change-email/request", () => {
    return HttpResponse.json(
      profileMessage(
        "Si el correo es válido y está disponible, te enviamos un enlace de confirmación a la nueva dirección.",
      ),
    );
  }),

  // POST /api/profile/change-email/confirm
  http.post("*/api/profile/change-email/confirm", () => {
    return HttpResponse.json(
      profileMessage(
        "Tu correo fue actualizado. Inicia sesión con tu nueva dirección.",
      ),
    );
  }),
];

// ---------------------------------------------------------------------------
// Variant handlers for error scenarios
// ---------------------------------------------------------------------------

/** PATCH /api/profile/basic — 422 validation error */
export const basicUpdateValidationErrorHandler = http.patch(
  "*/api/profile/basic",
  () =>
    HttpResponse.json(
      { detail: [{ msg: "Field required", loc: ["body", "first_name"] }] },
      { status: 422 },
    ),
);

/** POST /api/profile/change-password — 400 wrong current password */
export const changePasswordWrongCurrentHandler = http.post(
  "*/api/profile/change-password",
  () =>
    HttpResponse.json(
      { detail: "La contraseña actual no es correcta." },
      { status: 400 },
    ),
);

/** POST /api/profile/change-email/request — 400 wrong current password */
export const emailRequestWrongPasswordHandler = http.post(
  "*/api/profile/change-email/request",
  () =>
    HttpResponse.json(
      { detail: "La contraseña actual no es correcta." },
      { status: 400 },
    ),
);

/** POST /api/profile/change-email/confirm — 404 unknown token */
export const confirmEmailNotFoundHandler = http.post(
  "*/api/profile/change-email/confirm",
  () =>
    HttpResponse.json({ detail: "Enlace no válido." }, { status: 404 }),
);

/** POST /api/profile/change-email/confirm — 410 expired/used */
export const confirmEmailExpiredHandler = http.post(
  "*/api/profile/change-email/confirm",
  () =>
    HttpResponse.json(
      {
        detail:
          "El enlace ha expirado o ya fue utilizado. Solicita el cambio nuevamente.",
      },
      { status: 410 },
    ),
);

/** POST /api/profile/change-email/confirm — 409 email taken */
export const confirmEmailConflictHandler = http.post(
  "*/api/profile/change-email/confirm",
  () =>
    HttpResponse.json(
      {
        detail:
          "No se pudo aplicar el cambio. Solicita el cambio nuevamente.",
      },
      { status: 409 },
    ),
);
