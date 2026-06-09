/**
 * MSW handlers for the Session AI Assistant module (Feature 006).
 *
 * Covers:
 *   POST /api/clubs/:clubId/session-assistant/clarify
 *   POST /api/clubs/:clubId/session-assistant/draft
 *
 * Happy paths and error variants (503, 422).  Individual suites import and
 * push handlers with `mswServer.use(...)` to avoid polluting the global
 * handler registry.
 *
 * Privacy note: these mock responses contain no real athlete PII — they use
 * generic Spanish labels and option descriptions only.
 */
import { http, HttpResponse } from "msw";

import type { SessionClarifyResponse, SessionDraftResponse } from "@/api/sessionAssistant";

// ---------------------------------------------------------------------------
// Happy path fixtures
// ---------------------------------------------------------------------------

export const mockClarifyResponse: SessionClarifyResponse = {
  questions: [
    {
      id: "q1",
      header: "Grupo",
      question: "¿Para qué grupo es la sesión?",
      multi_select: false,
      allow_other: true,
      options: [
        { label: "10-12 años", description: "80% juego, sin intervalos estructurados" },
        { label: "13-15 años", description: "Máx 2 sesiones intensas por semana" },
        { label: "Mixto", description: "Ambos grupos juntos" },
      ],
    },
    {
      id: "q2",
      header: "Enfoque",
      question: "¿Qué quieres priorizar?",
      multi_select: true,
      allow_other: true,
      options: [
        { label: "Técnica de bajada", description: "Habilidad antes que fondo" },
        { label: "Resistencia Z1-Z2", description: "Base aeróbica suave" },
        { label: "Diversión / juego", description: "Formato lúdico" },
      ],
    },
  ],
  model: "gemini-2.5-flash-lite",
};

export const mockDraftResponse: SessionDraftResponse = {
  technical_focus: "Técnica de descenso en terreno suelto",
  objectives: "Mejorar trazada y control de frenada en bajada; mantener cadencia ≥70 rpm.",
  description:
    "CALENTAMIENTO (15 min): rodaje suave Z1 + movilidad articular.\n" +
    "PARTE PRINCIPAL (55 min): 4 repeticiones de tramo técnico de bajada con feedback.\n" +
    "VUELTA A LA CALMA (20 min): rodaje Z1 + estiramientos.",
  duration_min: 90,
  session_kind: "salida",
  location: "La Cumbre",
  scheduled_date: null,
  scheduled_start_time: null,
  athlete_call_up: "grupo_13_15",
  notes: "Faltan ~12 días para una válida prioridad A: intensidad moderada, sin sobrecarga.",
  model: "gemini-2.5-flash-lite",
};

/** 0 questions — client should call /draft directly */
export const mockClarifyEmptyResponse: SessionClarifyResponse = {
  questions: [],
  model: "gemini-2.5-flash-lite",
};

// ---------------------------------------------------------------------------
// Default handlers (happy path)
// ---------------------------------------------------------------------------

export const sessionAssistantHandlers = [
  // POST /api/clubs/:clubId/session-assistant/clarify — happy path
  http.post("*/api/clubs/:clubId/session-assistant/clarify", () => {
    return HttpResponse.json(mockClarifyResponse);
  }),

  // POST /api/clubs/:clubId/session-assistant/draft — happy path
  http.post("*/api/clubs/:clubId/session-assistant/draft", () => {
    return HttpResponse.json(mockDraftResponse);
  }),
];

// ---------------------------------------------------------------------------
// Error variant handlers (used with mswServer.use(...) in specific suites)
// ---------------------------------------------------------------------------

/** 503 — AI unavailable / disabled / timeout */
export const clarify503Handler = http.post(
  "*/api/clubs/:clubId/session-assistant/clarify",
  () =>
    HttpResponse.json(
      { detail: "El asistente no está disponible en este momento." },
      { status: 503 },
    ),
);

export const draft503Handler = http.post(
  "*/api/clubs/:clubId/session-assistant/draft",
  () =>
    HttpResponse.json(
      { detail: "El asistente no está disponible en este momento." },
      { status: 503 },
    ),
);

/** 422 — invalid request / guardrail violation */
export const clarify422Handler = http.post(
  "*/api/clubs/:clubId/session-assistant/clarify",
  () =>
    HttpResponse.json(
      { detail: "La solicitud no es válida. Revisa el texto e inténtalo de nuevo." },
      { status: 422 },
    ),
);

export const draft422Handler = http.post(
  "*/api/clubs/:clubId/session-assistant/draft",
  () =>
    HttpResponse.json(
      { detail: "La solicitud no es válida. Revisa el texto e inténtalo de nuevo." },
      { status: 422 },
    ),
);

/** Empty clarify — no questions, go straight to draft */
export const clarifyEmptyHandler = http.post(
  "*/api/clubs/:clubId/session-assistant/clarify",
  () => HttpResponse.json(mockClarifyEmptyResponse),
);
