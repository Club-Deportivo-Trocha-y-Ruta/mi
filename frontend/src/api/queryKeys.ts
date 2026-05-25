/**
 * Factories tipadas de queryKeys por dominio.
 *
 * Convención:
 * - `all` → namespace raíz (invalidación masiva por dominio).
 * - Sub-keys siempre `[...domain.all, "verb", ...args] as const` para
 *   que TanStack haga match por prefijo en `invalidateQueries`.
 * - Privacy R2: hooks dual-rol incluyen `userId` para aislar cache
 *   entre cuentas (tablets familiares).
 */

// ---------------------------------------------------------------------------
// Training sessions
// ---------------------------------------------------------------------------

/**
 * Para preservar la forma de los queryKeys ya en producción (y tests),
 * mantenemos los tres namespaces históricos como ramas paralelas:
 * - `lists` → "training-sessions"
 * - `details` → "training-session"
 * - `attendances` → "training-session-attendance"
 *
 * Los helpers `all` / `lists` / `details` / `attendances` permiten
 * invalidar masivamente por rama.
 */
export const trainingSessionKeys = {
  all: ["training-sessions"] as const,
  lists: ["training-sessions"] as const,
  list: (userId: number | null, filters?: unknown) =>
    ["training-sessions", userId, filters] as const,
  details: ["training-session"] as const,
  detail: (userId: number | null, id: number) =>
    ["training-session", userId, id] as const,
  attendances: ["training-session-attendance"] as const,
  attendance: (userId: number | null, sessionId: number) =>
    ["training-session-attendance", userId, sessionId] as const,
};

// ---------------------------------------------------------------------------
// Monthly reports
// ---------------------------------------------------------------------------

/**
 * Mantiene los dos namespaces históricos:
 * - `lists` → "monthly-reports"
 * - `details` → "monthly-report"
 */
export const monthlyReportKeys = {
  all: ["monthly-reports"] as const,
  lists: ["monthly-reports"] as const,
  list: (clubId: number | undefined) =>
    ["monthly-reports", clubId] as const,
  details: ["monthly-report"] as const,
  detail: (clubId: number | undefined, year: number, month: number) =>
    ["monthly-report", clubId, year, month] as const,
};

// ---------------------------------------------------------------------------
// Parent sessions / summary
// ---------------------------------------------------------------------------

/**
 * Mantiene los namespaces históricos (cada hook tenía su raíz propia):
 * - `sessionsList` → "parent-sessions"
 * - `summary` → "parent-monthly-summary"
 * - `nextSession` → "parent-next-session"
 * - `lastSession` → "parent-last-session"
 */
export const parentSessionKeys = {
  sessions: ["parent-sessions"] as const,
  list: (userId: number | null, filters?: unknown, athleteIds?: number[]) =>
    ["parent-sessions", userId, filters, athleteIds] as const,
  monthlySummary: (
    userId: number | null,
    year: number,
    month: number,
    athleteId?: number,
  ) =>
    [
      "parent-monthly-summary",
      userId,
      year,
      month,
      athleteId,
    ] as const,
  nextSession: (userId: number | null, athleteId: number | null) =>
    ["parent-next-session", userId, athleteId] as const,
  lastSession: (userId: number | null, athleteId: number | null) =>
    ["parent-last-session", userId, athleteId] as const,
};

// ---------------------------------------------------------------------------
// Session media
// ---------------------------------------------------------------------------

export const sessionMediaKeys = {
  all: ["training-session-media"] as const,
  list: (userId: number | null, sessionId: number) =>
    ["training-session-media", userId, sessionId] as const,
};

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

export const calendarKeys = {
  all: ["calendar"] as const,
  events: (filters?: unknown) => ["calendar", "events", filters] as const,
  eventsAll: ["calendar", "events"] as const,
  event: (id: number | null) => ["calendar", "event", id] as const,
  eventAll: ["calendar", "event"] as const,
  attendances: (eventId: number | null) =>
    ["calendar", "attendances", eventId] as const,
  attendancesAll: ["calendar", "attendances"] as const,
  availableRaceEvents: (season: number | null | undefined) =>
    ["calendar", "race-events", "available-for-calendar", season] as const,
};

// ---------------------------------------------------------------------------
// Athletes
// ---------------------------------------------------------------------------

export const athleteKeys = {
  all: ["athletes"] as const,
  list: (filters?: unknown) => ["athletes", filters] as const,
  detail: (id: number) => ["athlete", id] as const,
  detailAll: ["athlete"] as const,
  dashboardStats: () => ["dashboard-stats"] as const,
  dashboardAthleteDetails: (athleteIds: number[]) =>
    ["dashboard-athlete-details", athleteIds] as const,
  distribution: (
    athleteId: number,
    season: number | null | undefined,
    validaNum: number | null | undefined,
  ) => ["athlete-distribution", athleteId, season, validaNum] as const,
  evolution: (
    athleteId: number,
    season: number | null | undefined,
    metric: string | null | undefined,
  ) => ["athlete-evolution", athleteId, season, metric] as const,
  insightDetail: (athleteId: number, insightId: number | null | undefined) =>
    ["athlete-insight-detail", athleteId, insightId] as const,
  insights: (athleteId: number, params?: unknown) =>
    ["athlete-insights", athleteId, params ?? {}] as const,
  insightsAll: ["athlete-insights"] as const,
  runs: (athleteId: number, params?: unknown) =>
    ["athlete-runs", athleteId, params ?? {}] as const,
  runsAll: ["athlete-runs"] as const,
  growthMetrics: (id: number) => ["growth-metrics", id] as const,
  alerts: (params?: unknown) => ["alerts", params] as const,
};

// ---------------------------------------------------------------------------
// Anthropometry
// ---------------------------------------------------------------------------

export const anthropometryKeys = {
  all: ["anthropometry"] as const,
  list: (athleteId: number) => [...anthropometryKeys.all, athleteId] as const,
  aiPhv: (athleteId: number) => ["ai", "phv", athleteId] as const,
};

// ---------------------------------------------------------------------------
// Parents (users / athletes / invites)
// ---------------------------------------------------------------------------

export const parentKeys = {
  athletes: (params?: unknown) => ["parent-athletes", params] as const,
  athletesAll: () => ["parent-athletes"] as const,
  users: (params?: unknown) => ["parent-users", params] as const,
  usersAll: () => ["parent-users"] as const,
  myAthletes: (userId: number | null) => ["my-athletes", userId] as const,
  invites: (athleteId: number) => ["parent-invites", athleteId] as const,
  invitesAll: () => ["parent-invites"] as const,
  activeAthlete: (userId: number | null) =>
    ["parents", "active-athlete", userId] as const,
};

// ---------------------------------------------------------------------------
// Consent
// ---------------------------------------------------------------------------

export const consentKeys = {
  activePolicy: () => ["active-policy"] as const,
  myStatus: (userId: number | null) => ["my-consent", userId] as const,
  myStatusAll: ["my-consent"] as const,
};

// ---------------------------------------------------------------------------
// Onboarding
// ---------------------------------------------------------------------------

export const onboardingKeys = {
  inviteToken: (token: string | null) => ["invite-token", token] as const,
};

// ---------------------------------------------------------------------------
// AI health
// ---------------------------------------------------------------------------

export const aiHealthKeys = {
  all: ["ai"] as const,
  health: () => [...aiHealthKeys.all, "health"] as const,
};
