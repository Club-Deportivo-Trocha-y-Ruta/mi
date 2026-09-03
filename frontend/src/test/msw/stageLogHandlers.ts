/**
 * MSW handlers para la Bitácora (StageLog), feature 038, T204.
 *
 * Cubre los endpoints coach nuevos (regenerate-block, render) y el router
 * de padres (`parent_newsletters.py`). Sigue el patrón de
 * `src/test/msw/newsletterHandlers.ts`.
 *
 * Privacy constraint: `sent_to` / emails en claro NUNCA aparecen en ninguna
 * respuesta — `delivery[].email_masked` ya viene enmascarado del backend.
 */
import { http, HttpResponse } from "msw";

import type {
  ParentNewsletterListItem,
  ParentNewsletterOut,
} from "@/api/parentNewsletters";
import type { AthleteNewsletter } from "@/types/athleteNewsletter.types";
import type { ParentStageLog } from "@/types/stageLog.types";
import { makeNewsletter } from "@/test/msw/newsletterHandlers";
import {
  buildStageLogFullMonth,
  buildStageLogTrainingOnlyMonth,
} from "@/test/fixtures/stageLog";

// ---------------------------------------------------------------------------
// Fixture factories
// ---------------------------------------------------------------------------

export function makeV2Newsletter(
  overrides?: Partial<AthleteNewsletter>,
): AthleteNewsletter {
  return makeNewsletter({
    stage_log: buildStageLogFullMonth(),
    stage_overrides: null,
    hidden_blocks: [],
    coach_note: buildStageLogFullMonth().coach_note,
    ...overrides,
  });
}

export function toParentStageLog(
  stageLog = buildStageLogTrainingOnlyMonth(),
): ParentStageLog {
  const { block_states: _blockStates, grounding_violations: _violations, analyst_reading, ...rest } =
    stageLog;
  return {
    ...rest,
    analyst_reading: analyst_reading
      ? {
          headline_family: analyst_reading.headline_family,
          action_family: analyst_reading.action_family,
          valida_label: analyst_reading.valida_label,
        }
      : null,
  };
}

export function makeParentNewsletterListItem(
  overrides?: Partial<ParentNewsletterListItem>,
): ParentNewsletterListItem {
  return {
    id: 1,
    athlete_id: 42,
    year: 2026,
    month: 7,
    period_label: "Julio 2026",
    stage_title: "Un mes de base, sin carreras, construyendo resistencia",
    sent_at: "2026-08-02T10:00:00Z",
    read_at: null,
    ...overrides,
  };
}

export function makeParentNewsletterOut(
  overrides?: Partial<ParentNewsletterOut>,
): ParentNewsletterOut {
  return {
    id: 1,
    athlete_id: 42,
    year: 2026,
    month: 7,
    period_label: "Julio 2026",
    sent_at: "2026-08-02T10:00:00Z",
    read_at: null,
    has_pdf: true,
    stage_log: toParentStageLog(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers — coach
// ---------------------------------------------------------------------------

export const stageLogHandlers = [
  // POST /api/athletes/:athleteId/monthly-newsletters/:id/regenerate-block
  http.post(
    "*/api/athletes/:athleteId/monthly-newsletters/:id/regenerate-block",
    async ({ params }) => {
      const athleteId = Number(params.athleteId);
      const id = Number(params.id);
      return HttpResponse.json(makeV2Newsletter({ id, athlete_id: athleteId }));
    },
  ),

  // GET /api/athletes/:athleteId/monthly-newsletters/:id/render?surface=email
  http.get(
    "*/api/athletes/:athleteId/monthly-newsletters/:id/render",
    () => {
      return new HttpResponse(
        "<html><body><p>Bitácora de Atleta Demo</p></body></html>",
        { status: 200, headers: { "Content-Type": "text/html" } },
      );
    },
  ),

  // -------------------------------------------------------------------------
  // Handlers — padre
  // -------------------------------------------------------------------------

  // GET /api/parents/me/athletes/:athleteId/newsletters
  http.get(
    "*/api/parents/me/athletes/:athleteId/newsletters",
    ({ params }) => {
      const athleteId = Number(params.athleteId);
      return HttpResponse.json([
        makeParentNewsletterListItem({ athlete_id: athleteId }),
        makeParentNewsletterListItem({
          id: 2,
          athlete_id: athleteId,
          month: 6,
          period_label: "Junio 2026",
          read_at: "2026-07-05T09:00:00Z",
        }),
      ]);
    },
  ),

  // GET /api/parents/me/athletes/:athleteId/newsletters/:newsletterId
  http.get(
    "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId",
    ({ params }) => {
      const athleteId = Number(params.athleteId);
      const newsletterId = Number(params.newsletterId);
      return HttpResponse.json(
        makeParentNewsletterOut({ id: newsletterId, athlete_id: athleteId }),
      );
    },
  ),

  // GET /api/parents/me/athletes/:athleteId/newsletters/:newsletterId/pdf
  http.get(
    "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId/pdf",
    () => {
      const pdfContent = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // %PDF header
      return new HttpResponse(pdfContent, {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": "attachment; filename=bitacora.pdf",
        },
      });
    },
  ),

  // POST /api/parents/me/athletes/:athleteId/newsletters/:newsletterId/read
  http.post(
    "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId/read",
    () => {
      return new HttpResponse(null, { status: 204 });
    },
  ),
];

// ---------------------------------------------------------------------------
// Variant handlers for error scenarios
// ---------------------------------------------------------------------------

/** 409 al regenerar un bloque de un boletín ya enviado. */
export const regenerateBlockSentConflictHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters/:id/regenerate-block",
  () => {
    return HttpResponse.json(
      { detail: "No se puede regenerar un boletín ya enviado." },
      { status: 409 },
    );
  },
);

/** 451 al regenerar sin consentimiento IA. */
export const regenerateBlockConsentMissingHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters/:id/regenerate-block",
  () => {
    return HttpResponse.json(
      { detail: "Falta el consentimiento de IA para este atleta." },
      { status: 451 },
    );
  },
);

/** 503 cuando el proveedor de IA falla al regenerar. */
export const regenerateBlockProviderErrorHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters/:id/regenerate-block",
  () => {
    return HttpResponse.json(
      { detail: "El proveedor de IA no respondió. Intenta de nuevo." },
      { status: 503 },
    );
  },
);

/** 404 en el detalle del padre: no enviado o no vinculado. */
export const parentNewsletterNotFoundHandler = http.get(
  "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId",
  () => {
    return HttpResponse.json({ detail: "Not found" }, { status: 404 });
  },
);

/** 403 en las rutas de padre cuando el caller es coach/admin. */
export const parentNewsletterForbiddenHandler = http.get(
  "*/api/parents/me/athletes/:athleteId/newsletters",
  () => {
    return HttpResponse.json(
      { detail: "No tienes permiso para realizar esta acción." },
      { status: 403 },
    );
  },
);
