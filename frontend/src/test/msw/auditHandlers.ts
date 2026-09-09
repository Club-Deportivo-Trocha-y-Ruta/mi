/**
 * MSW handlers del historial de auditoría (feature 041 — gobernanza
 * multi-coach).
 *
 * Cubre:
 *   - GET /api/clubs/:clubId/audit-log
 *   - GET /api/athletes/:athleteId/audit-log
 *   - GET /api/audit/reason-codes
 *
 * `auditHandlers` sirve datos sintéticos sin PII de menores (ninguna fila
 * lleva nombre, fecha de nacimiento ni medida de un atleta — solo
 * `athlete_id`), consistente con research R-33 y el escaneo del contrato
 * (audit-log-api.md §13 T8). Los tests de pickers de motivo en otros
 * features (archivo de atleta, staff) reutilizan `auditReasonCodesHandler`
 * para no declarar su propio arreglo de códigos.
 */
import { http, HttpResponse } from "msw";

import type {
  AuditEntryOut,
  AuditListOut,
  AuditReasonCodeListOut,
} from "@/types/audit.types";

export function makeAuditEntry(overrides?: Partial<AuditEntryOut>): AuditEntryOut {
  return {
    id: 1,
    occurred_at: "2026-03-14T22:05:41.482913",
    actor_user_id: 10,
    actor_kind: "user",
    actor_role: "coach",
    actor_display_name: "Ana Coach",
    action: "update",
    entity_type: "training_session",
    entity_id: 55,
    entity_label: "la sesión de entrenamiento",
    club_id: 1,
    athlete_id: null,
    reason_code: null,
    reason_label: null,
    sentence_es: "Ana Coach actualizó la sesión de entrenamiento.",
    request_id: "9f1c2b7a4d5e46a8b0c3d9e2f1a7b6c4",
    detail: {
      changed_fields: ["scheduled_date"],
      changed_field_labels: ["Fecha programada"],
      diff: {
        scheduled_date: { before: "2026-03-10", after: "2026-03-14" },
      },
      meta: null,
    },
    ...overrides,
  };
}

export function makeAuditListOut(
  overrides?: Partial<AuditListOut>,
): AuditListOut {
  const items = overrides?.items ?? [makeAuditEntry()];
  return {
    items,
    total: overrides?.total ?? items.length,
    limit: overrides?.limit ?? 15,
    offset: overrides?.offset ?? 0,
  };
}

export function makeAuditReasonCodeListOut(
  overrides?: Partial<AuditReasonCodeListOut>,
): AuditReasonCodeListOut {
  return {
    items: overrides?.items ?? [
      { code: "athlete_left_club", group: "athlete_archive", label: "Se retiró del club" },
      { code: "athlete_transferred", group: "athlete_archive", label: "Traslado a otro club" },
      {
        code: "athlete_season_inactive",
        group: "athlete_archive",
        label: "Inactivo esta temporada",
      },
      {
        code: "athlete_family_request",
        group: "athlete_archive",
        label: "Solicitud de la familia",
      },
      {
        code: "athlete_duplicate_record",
        group: "athlete_archive",
        label: "Registro duplicado",
      },
      { code: "athlete_data_correction", group: "athlete_archive", label: "Corrección de datos" },
    ],
  };
}

export const clubAuditLogHandler = http.get(
  "*/api/clubs/:clubId/audit-log",
  () => HttpResponse.json(makeAuditListOut()),
);

export const athleteAuditLogHandler = http.get(
  "*/api/athletes/:athleteId/audit-log",
  () => HttpResponse.json(makeAuditListOut()),
);

export const auditReasonCodesHandler = http.get(
  "*/api/audit/reason-codes",
  () => HttpResponse.json(makeAuditReasonCodeListOut()),
);

export const auditHandlers = [
  clubAuditLogHandler,
  athleteAuditLogHandler,
  auditReasonCodesHandler,
];

export const clubAuditLogErrorHandler = http.get(
  "*/api/clubs/:clubId/audit-log",
  () => HttpResponse.json({ detail: "Error interno del servidor" }, { status: 500 }),
);

export const clubAuditLogForbiddenHandler = http.get(
  "*/api/clubs/:clubId/audit-log",
  () =>
    HttpResponse.json(
      { detail: "No tienes permisos para ver el historial de este club." },
      { status: 403 },
    ),
);
