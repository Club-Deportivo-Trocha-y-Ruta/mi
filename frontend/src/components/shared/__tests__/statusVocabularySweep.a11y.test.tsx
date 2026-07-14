/**
 * statusVocabularySweep.a11y — barrido de accesibilidad transversal (T024,
 * feature 033) sobre los 8 puntos de migración de
 * `contracts/status-vocabulary-sweep.md` (T016–T023): confirma que CADA
 * estado posible de CADA componente migrado renderiza `<StatusBadge>` sin
 * violaciones jest-axe y siempre pareando ícono + etiqueta (Constitution
 * III — el color nunca es el único canal).
 *
 * No repite la cobertura funcional (labels, colores, callbacks) ya cubierta
 * por el test suite propio de cada componente — solo el eje transversal
 * accesibilidad × "todo estado pasa por StatusBadge".
 *
 * Dos componentes (`AthleteAIAnalysisTab`'s confidence badge y
 * `AthleteNewslettersDashboardPage`'s card badge) no exponen su
 * sub-componente de badge como export propio y ya tienen su propia suite
 * de axe end-to-end (ver `AthleteAIAnalysisTab.test.tsx` /
 * `AthleteNewslettersDashboardPage.test.tsx`) — aquí se valida
 * exhaustivamente, para CADA estado que esos componentes pueden recibir,
 * la composición exacta que ambos renderizan verbatim en su call site
 * (`<StatusBadge status={adapter(...).status} label={adapter(...).label} />`,
 * sin markup adicional entre el adaptador y StatusBadge), completando así
 * el barrido de los 8 sin duplicar sus mocks de página completa.
 */
import { describe, it, expect } from "vitest";
import { createElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helper genérico: toda instancia de StatusBadge en el DOM pareó ícono+label
// ---------------------------------------------------------------------------

/** Cada `<span>` de StatusBadge trae un `<svg aria-hidden="true">` junto al
 * texto — nunca solo color. Verifica esto para cada label esperado. */
function expectIconLabelPairing(labels: string[]) {
  for (const label of labels) {
    const els = screen.getAllByText(label);
    for (const el of els) {
      const badge = el.closest("span");
      expect(badge).toBeInTheDocument();
      const icon = badge?.querySelector("svg");
      expect(icon).toBeInTheDocument();
      expect(icon).toHaveAttribute("aria-hidden", "true");
    }
  }
}

async function expectNoAxeViolations(container: HTMLElement) {
  const results = await axe(container);
  expect(results).toHaveNoViolations();
}

// ---------------------------------------------------------------------------
// 1. ConnectionStatusBadge — 4 estados
// ---------------------------------------------------------------------------

import { ConnectionStatusBadge } from "@/components/activities/ConnectionStatusBadge";
import type { StravaConnectionStatus } from "@/types/strava.types";

describe("Sweep §1 — ConnectionStatusBadge", () => {
  const STATES: StravaConnectionStatus[] = ["none", "active", "broken", "disconnected"];
  const LABELS: Record<StravaConnectionStatus, string> = {
    none: "Sin conectar",
    active: "Conectado",
    broken: "Conexión rota",
    disconnected: "Desconectado",
  };

  it.each(STATES)("estado=%s — 0 violaciones axe + ícono+label pareados", async (state) => {
    const { container } = render(<ConnectionStatusBadge status={state} />);
    expectIconLabelPairing([LABELS[state]]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 2. CompetitionStatusBadges — 3 sub-badges, cada combinación relevante
// ---------------------------------------------------------------------------

import { CompetitionStatusBadges } from "@/components/competitions/CompetitionStatusBadges";
import { makeRaceEventListItem } from "@/test/msw/raceEventsHandlers";
import type { RaceEventListItem } from "@/types/raceEvents.types";

describe("Sweep §2 — CompetitionStatusBadges", () => {
  const CASES: Array<[string, Partial<RaceEventListItem>, string[]]> = [
    [
      "todo completo",
      { has_results: true, has_calendar_event: true, conditions_completeness: "complete" },
      ["Con resultados", "Calendario", "Condiciones OK"],
    ],
    [
      "todo vacío",
      { has_results: false, has_calendar_event: false, conditions_completeness: "empty" },
      ["Sin resultados", "Sin calendario", "Sin condiciones"],
    ],
    [
      "condiciones parciales",
      { conditions_completeness: "partial" },
      ["Condiciones parciales"],
    ],
  ];

  it.each(CASES)("%s — 0 violaciones axe + ícono+label pareados", async (_name, overrides, labels) => {
    const { container } = render(
      <CompetitionStatusBadges item={makeRaceEventListItem(overrides)} />,
    );
    expectIconLabelPairing(labels);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 3. SessionStatusBadge — 3 estados
// ---------------------------------------------------------------------------

import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import type { SessionStatus } from "@/types/trainingSession.types";

describe("Sweep §3 — SessionStatusBadge", () => {
  const STATES: SessionStatus[] = ["planned", "executed", "cancelled"];
  const LABELS: Record<SessionStatus, string> = {
    planned: "Planificada",
    executed: "Ejecutada",
    cancelled: "Cancelada",
  };

  it.each(STATES)("estado=%s — 0 violaciones axe + ícono+label pareados", async (state) => {
    const { container } = render(<SessionStatusBadge status={state} />);
    expectIconLabelPairing([LABELS[state]]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 4. AI insight confidence (lib/insights.ts confidenceStatus + StatusBadge)
//
// AthleteAIAnalysisTab.tsx:254-257 renderiza
// `<StatusBadge status={confidenceStatus(latest.confidence).status}
//               label={confidenceStatus(latest.confidence).label} />`
// verbatim (sin wrapper adicional que afecte a11y) — se valida aquí la
// composición exacta para los 3 estados posibles, sin re-montar la página
// completa (ya cubierta en AthleteAIAnalysisTab.test.tsx con confidence="high").
// ---------------------------------------------------------------------------

import { confidenceStatus } from "@/lib/insights";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { InsightConfidence } from "@/types/athleteRaceAnalysis.types";

describe("Sweep §4 — AI insight confidence badge (AthleteAIAnalysisTab call site)", () => {
  const STATES: InsightConfidence[] = ["high", "medium", "low"];

  it.each(STATES)("confidence=%s — 0 violaciones axe + ícono+label pareados", async (confidence) => {
    const badge = confidenceStatus(confidence);
    const { container } = render(
      <StatusBadge status={badge.status} label={badge.label} />,
    );
    expectIconLabelPairing([badge.label]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 5. Newsletter status (AthleteNewslettersDashboardPage call site)
//
// AthleteNewsletterCard (interno, no exportado) renderiza
// `<StatusBadge status={badge.status} label={badge.label} />` verbatim en
// AthleteNewslettersDashboardPage.tsx:172-174 — se valida la composición
// exacta para los 5 estados posibles sin remontar la página completa (ya
// cubierta funcionalmente en AthleteNewslettersDashboardPage.test.tsx).
// ---------------------------------------------------------------------------

import { newsletterStatus } from "@/routes/training/AthleteNewslettersDashboardPage";
import type { NewsletterStatus } from "@/types/athleteNewsletter.types";

describe("Sweep §5 — Newsletter status badge (AthleteNewslettersDashboardPage call site)", () => {
  const STATES: Array<NewsletterStatus | "none"> = ["none", "draft", "approved", "sent", "failed"];

  it.each(STATES)("status=%s — 0 violaciones axe + ícono+label pareados", async (status) => {
    const badge = newsletterStatus(status);
    const { container } = render(
      <StatusBadge status={badge.status} label={badge.label} />,
    );
    expectIconLabelPairing([badge.label]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 6. ConsentStatusPanel — 4 estados de consentimiento + 2 del sub-toggle IA
// ---------------------------------------------------------------------------

const mockRenewMutate = vi.fn();
vi.mock("@/hooks/consent", () => ({
  useRenewConsent: () => ({ mutate: mockRenewMutate, isPending: false, isError: false }),
  useWithdrawConsent: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ConsentStatusPanel } from "@/components/consent/ConsentStatusPanel";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";

function makeConsentQueryWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client }, createElement(MemoryRouter, null, children));
}

const activePolicy: PrivacyPolicySummary = {
  id: 2,
  version: "v1.2",
  effective_date: "2026-05-15",
  title: "Política de Tratamiento de Datos Personales",
  changelog: null,
};

function makeConsentAthlete(
  overrides: Partial<AthleteConsentStatus["current_consent"]> | null,
  aiActive: boolean,
): AthleteConsentStatus {
  if (overrides === null) {
    return { athlete_id: 1, athlete_name: "Atleta Sin Consentimiento", current_consent: null };
  }
  return {
    athlete_id: 1,
    athlete_name: "Atleta Prueba",
    current_consent: {
      id: 10,
      policy_version: "v1.1",
      consented_at: "2026-05-15T09:00:00Z",
      is_current_policy: true,
      withdrawn_at: null,
      grants: {
        data_collection: true,
        anthropometry: true,
        training_tracking: false,
        third_party_sharing: aiActive,
      },
      ...overrides,
    },
  };
}

describe("Sweep §6 — ConsentStatusPanel", () => {
  const CASES: Array<[string, AthleteConsentStatus, string[]]> = [
    ["never", makeConsentAthlete(null, false), ["Sin consentimiento"]],
    [
      "outdated (+ IA activa)",
      makeConsentAthlete({ is_current_policy: false }, true),
      ["Desactualizado", "IA: activa"],
    ],
    [
      "revoked",
      makeConsentAthlete({ withdrawn_at: "2026-06-01T00:00:00Z" }, false),
      ["Revocado"],
    ],
    [
      "current (+ IA no autorizada)",
      makeConsentAthlete({}, false),
      ["Vigente", "IA: no autorizada"],
    ],
  ];

  it.each(CASES)("%s — 0 violaciones axe + ícono+label pareados", async (_name, athlete, labels) => {
    const { container } = render(
      <ConsentStatusPanel consentsPerAthlete={[athlete]} activePolicy={activePolicy} />,
      { wrapper: makeConsentQueryWrapper() },
    );
    // Expandir el panel para que los badges por atleta sean visibles.
    fireEvent.click(screen.getByRole("button", { name: /Gestionar consentimiento/i }));
    expectIconLabelPairing(labels);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 7. StaleAnalysisBadge — único estado (stale)
// ---------------------------------------------------------------------------

vi.mock("@/hooks/ai/useRaceRun", () => ({
  useReExecuteRun: () => ({ mutate: vi.fn(), isPending: false }),
  useRunStatus: () => ({ data: undefined, isLoading: false }),
  isTerminalState: () => false,
}));

import { StaleAnalysisBadge } from "@/components/competitions/insights/StaleAnalysisBadge";

describe("Sweep §7 — StaleAnalysisBadge", () => {
  it("estado stale — 0 violaciones axe + ícono+label pareados", async () => {
    const { container } = render(<StaleAnalysisBadge runId="run-abc" />);
    expectIconLabelPairing(["Análisis desactualizado"]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 8. GroupRunRow — todos los estados terminales (StateChip eliminado, T023)
// ---------------------------------------------------------------------------

vi.mock("@/components/ai/HITLApprovalCard", () => ({
  HITLApprovalCard: () => null,
}));

import { GroupRunRow } from "@/components/competitions/insights/GroupRunRow";
import type { TrackedRunEntry } from "@/hooks/ai/useGroupAnalysis";

function makeRunEntry(overrides: Partial<TrackedRunEntry>): TrackedRunEntry {
  return {
    athlete_id: 1,
    name: "Atleta Prueba",
    run_id: null,
    outcome: "started",
    detail: null,
    ...overrides,
  };
}

describe("Sweep §8 — GroupRunRow (estados terminales, sin runState en vivo)", () => {
  const CASES: Array<[string, TrackedRunEntry, string]> = [
    ["already_running", makeRunEntry({ outcome: "already_running" }), "Ya en curso"],
    [
      "backpressure",
      makeRunEntry({ outcome: "backpressure", detail: "Límite alcanzado, intenta luego." }),
      "Límite alcanzado",
    ],
    ["error", makeRunEntry({ outcome: "error" }), "Fallido"],
    ["no_results", makeRunEntry({ outcome: "no_results" }), "Fallido"],
    ["budget_exceeded", makeRunEntry({ outcome: "budget_exceeded" }), "Fallido"],
  ];

  it.each(CASES)("outcome=%s — 0 violaciones axe + ícono+label pareados", async (_name, entry, label) => {
    const { container } = render(
      <ul>
        <GroupRunRow entry={entry} />
      </ul>,
    );
    expectIconLabelPairing([label]);
    await expectNoAxeViolations(container);
  });
});
