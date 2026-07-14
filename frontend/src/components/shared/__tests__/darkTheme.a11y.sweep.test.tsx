/**
 * Dark-theme a11y sweep (feature 033, US5, T061).
 *
 * Forces `data-theme="dark"` on `document.documentElement` (the same
 * attribute `frontend/src/lib/theme.ts`'s `applyCoachTheme("dark")` sets —
 * see `contracts/dark-theme-tokens.md`) and re-runs `jest-axe` over every
 * page-level/dialog-level coach component this feature touches: the 8
 * migrated status badges (`contracts/status-vocabulary-sweep.md`), the new
 * "Atajos de teclado" help dialog (T063), and both charts (`chart-style.md`).
 *
 * Scope note: jsdom never loads `style.css` in this test suite (no `test.css`
 * config, no import in `src/test/setup.ts`), so `getComputedStyle` inside
 * jest-axe cannot see real resolved colors either way — forcing
 * `data-theme="dark"` cannot make axe's `color-contrast` rule (already
 * effectively inert in jsdom) newly fail OR newly pass. What this sweep DOES
 * exercise, and is the actual point of the "for data-theme=dark" wording:
 *   1. Structural regressions — if a future change makes any of these
 *      components branch on theme in JS (e.g. a `useTheme()`/`matchMedia`
 *      read that swaps markup, not just CSS), this is the harness that
 *      would catch a dark-mode-only a11y regression; today none of them do,
 *      so this doubles as a regression guard.
 *   2. Icon+label pairing (Constitution III) still holds with the attribute
 *      present — confirms no assertion helper accidentally depends on a
 *      light-only DOM shape.
 * Real token-math contrast auditing (the thing that actually needs numbers,
 * not markup) is T060's job (`dark-theme-contrast.test.ts`), not this file's.
 *
 * The "sweep for dark-on-dark invisible marks" half of T061 is the
 * `describe("dark-on-dark invisible-mark static sweep"...)` block at the
 * bottom — a source-text check (jsdom/axe cannot see resolved colors, so a
 * markup-level DOM check cannot catch a hardcoded-hex-bypasses-the-token
 * bug either; only reading the source can). It intentionally FAILS today —
 * see that block's comment and this task's summary for the two real
 * findings it surfaces.
 */
import { createElement } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import path from "node:path";

expect.extend(toHaveNoViolations);

function forceDarkTheme() {
  document.documentElement.setAttribute("data-theme", "dark");
}

function clearForcedTheme() {
  document.documentElement.removeAttribute("data-theme");
}

async function expectNoAxeViolations(container: HTMLElement) {
  const results = await axe(container);
  expect(results).toHaveNoViolations();
}

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

// ---------------------------------------------------------------------------
// 1. Status badges — one representative state per migrated component
//    (T016-T023). Full per-state enumeration already exists in light mode
//    (statusVocabularySweep.a11y.test.tsx, T024); dark mode changes only CSS
//    custom-property VALUES, never which markup branch renders, so a single
//    state per component is sufficient to catch a theme-conditional
//    regression without re-deriving the full state matrix here.
// ---------------------------------------------------------------------------

import { ConnectionStatusBadge } from "@/components/activities/ConnectionStatusBadge";
import { CompetitionStatusBadges } from "@/components/competitions/CompetitionStatusBadges";
import { makeRaceEventListItem } from "@/test/msw/raceEventsHandlers";
import { SessionStatusBadge } from "@/components/training/SessionStatusBadge";
import { confidenceStatus } from "@/lib/insights";
import { newsletterStatus } from "@/routes/training/AthleteNewslettersDashboardPage";
import { StatusBadge } from "@/components/shared/StatusBadge";

describe("T061 — dark-theme jest-axe sweep", () => {
  beforeEach(forceDarkTheme);
  afterEach(clearForcedTheme);

  it("ConnectionStatusBadge (active) — 0 violations under data-theme=dark", async () => {
    const { container } = render(<ConnectionStatusBadge status="active" />);
    expectIconLabelPairing(["Conectado"]);
    await expectNoAxeViolations(container);
  });

  it("CompetitionStatusBadges (all complete) — 0 violations under data-theme=dark", async () => {
    const { container } = render(
      <CompetitionStatusBadges
        item={makeRaceEventListItem({
          has_results: true,
          has_calendar_event: true,
          conditions_completeness: "complete",
        })}
      />,
    );
    expectIconLabelPairing(["Con resultados", "Calendario", "Condiciones OK"]);
    await expectNoAxeViolations(container);
  });

  it("SessionStatusBadge (executed) — 0 violations under data-theme=dark", async () => {
    const { container } = render(<SessionStatusBadge status="executed" />);
    expectIconLabelPairing(["Ejecutada"]);
    await expectNoAxeViolations(container);
  });

  it("confidenceStatus badge (high) — 0 violations under data-theme=dark", async () => {
    const badge = confidenceStatus("high");
    const { container } = render(<StatusBadge status={badge.status} label={badge.label} />);
    expectIconLabelPairing([badge.label]);
    await expectNoAxeViolations(container);
  });

  it("newsletterStatus badge (sent) — 0 violations under data-theme=dark", async () => {
    const badge = newsletterStatus("sent");
    const { container } = render(<StatusBadge status={badge.status} label={badge.label} />);
    expectIconLabelPairing([badge.label]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 2. ConsentStatusPanel + StaleAnalysisBadge + GroupRunRow — need their own
//    mocks (consent hooks / sonner / run-status hook / HITL card), mirroring
//    statusVocabularySweep.a11y.test.tsx exactly, one state each.
// ---------------------------------------------------------------------------

const mockRenewMutate = vi.fn();
vi.mock("@/hooks/consent", () => ({
  useRenewConsent: () => ({ mutate: mockRenewMutate, isPending: false, isError: false }),
  useWithdrawConsent: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/hooks/ai/useRaceRun", () => ({
  useReExecuteRun: () => ({ mutate: vi.fn(), isPending: false }),
  useRunStatus: () => ({ data: undefined, isLoading: false }),
  isTerminalState: () => false,
}));
vi.mock("@/components/ai/HITLApprovalCard", () => ({
  HITLApprovalCard: () => null,
}));

import { ConsentStatusPanel } from "@/components/consent/ConsentStatusPanel";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";
import { StaleAnalysisBadge } from "@/components/competitions/insights/StaleAnalysisBadge";
import { GroupRunRow } from "@/components/competitions/insights/GroupRunRow";
import type { TrackedRunEntry } from "@/hooks/ai/useGroupAnalysis";

function makeQueryWrapper() {
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

const consentAthlete: AthleteConsentStatus = {
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
      third_party_sharing: false,
    },
  },
};

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

describe("T061 — dark-theme jest-axe sweep (mocked-dependency components)", () => {
  beforeEach(forceDarkTheme);
  afterEach(clearForcedTheme);

  it("ConsentStatusPanel (current, AI not authorized) — 0 violations under data-theme=dark", async () => {
    const { container } = render(
      <ConsentStatusPanel consentsPerAthlete={[consentAthlete]} activePolicy={activePolicy} />,
      { wrapper: makeQueryWrapper() },
    );
    fireEvent.click(screen.getByRole("button", { name: /Gestionar consentimiento/i }));
    expectIconLabelPairing(["Vigente", "IA: no autorizada"]);
    await expectNoAxeViolations(container);
  });

  it("StaleAnalysisBadge — 0 violations under data-theme=dark", async () => {
    const { container } = render(<StaleAnalysisBadge runId="run-abc" />);
    expectIconLabelPairing(["Análisis desactualizado"]);
    await expectNoAxeViolations(container);
  });

  it("GroupRunRow (failed) — 0 violations under data-theme=dark", async () => {
    const { container } = render(
      <ul>
        <GroupRunRow entry={makeRunEntry({ outcome: "error" })} />
      </ul>,
    );
    expectIconLabelPairing(["Fallido"]);
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 3. KeyboardShortcutsDialog (T063) — the feature's own new dialog.
// ---------------------------------------------------------------------------

import { KeyboardShortcutsDialog } from "@/components/layout/KeyboardShortcutsDialog";

describe("T061 — dark-theme jest-axe sweep (dialog)", () => {
  beforeEach(forceDarkTheme);
  afterEach(clearForcedTheme);

  it("KeyboardShortcutsDialog (open) — 0 violations under data-theme=dark", async () => {
    const { container } = render(
      <KeyboardShortcutsDialog open onOpenChange={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("keyboard-shortcuts-dialog")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 4. Charts — DistributionChart / EvolutionChart, one happy-path mount each.
//    Recharts is stubbed the same way both charts' own suites already do
//    (real recharts + ResponsiveContainer hangs in jsdom, per their own
//    header comments) — this file needs its own copy of that mock since
//    vi.mock is file-scoped.
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  AreaChart: ({ children, data }: { children: React.ReactNode; data: unknown[] }) => (
    <div data-testid="area-chart" data-points={data.length}>
      {children}
    </div>
  ),
  LineChart: ({ children, data }: { children: React.ReactNode; data: unknown[] }) => (
    <div data-testid="line-chart" data-points={data.length}>
      {children}
    </div>
  ),
  Area: () => <div data-testid="recharts-area" />,
  Line: () => <div data-testid="recharts-line" />,
  CartesianGrid: (props: { stroke?: string; strokeDasharray?: string }) => (
    <div
      data-testid="recharts-grid"
      data-stroke={props.stroke}
      data-stroke-dasharray={props.strokeDasharray ?? ""}
    />
  ),
  XAxis: () => <div data-testid="recharts-x" />,
  YAxis: () => <div data-testid="recharts-y" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ReferenceLine: ({ label }: { label?: { value?: string } }) => (
    <div
      data-testid="recharts-ref-line"
      data-label={typeof label === "object" ? label?.value : undefined}
    />
  ),
}));

import { DistributionChart } from "@/components/athletes/ai/DistributionChart";
import { EvolutionChart } from "@/components/athletes/ai/EvolutionChart";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

describe("T061 — dark-theme jest-axe sweep (charts)", () => {
  beforeEach(forceDarkTheme);
  afterEach(clearForcedTheme);

  it("DistributionChart (high-confidence happy path) — 0 violations under data-theme=dark", async () => {
    const { container } = renderWithProviders(
      <DistributionChart athleteId={42} defaultEventId={100} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("EvolutionChart (happy path) — 0 violations under data-theme=dark", async () => {
    const { container } = renderWithProviders(
      <EvolutionChart athleteId={42} defaultSeason={2026} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("line-chart")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });
});

// ---------------------------------------------------------------------------
// 5. Dark-on-dark invisible-mark static sweep.
//
// jsdom/axe cannot evaluate resolved color contrast (no style.css loaded —
// see file header), so the only way to catch "this mark uses a hardcoded
// light-mode-only literal instead of a token that flips in dark mode" is to
// read the source and check which color value actually ships. This block
// intentionally targets the exact literal `rgba(34,42,53,0.08)` /
// `rgba(34,42,53,0.15)` — the light-only `--color-border-gray` VALUE
// (style.css `:root`) — appearing verbatim where a `var(--color-border-gray)`
// reference (or the `border-border-gray` Tailwind utility, which resolves to
// the same variable) is required for the mark to track the dark override
// `rgba(255,255,255,0.10)` (style.css `:root[data-theme="dark"]`).
//
// Both findings below are REAL, currently-unresolved dark-mode legibility
// bugs in this feature's own files (not the wider pre-existing app-wide
// rgba(34,42,53,...) literal usage in `ui/*` primitives and older routes,
// which `contracts/chart-style.md`'s own "Explicitly not touched by this
// contract" section assigns to `specs/028-frontend-design-foundation`'s
// shadow/token consolidation, out of scope here):
//
//   1. `DistributionChart.tsx`/`EvolutionChart.tsx`'s `<CartesianGrid
//      stroke="rgba(34,42,53,0.08)" />` — `contracts/chart-style.md`'s own
//      Grid rule claims this literal "already IS --color-border-gray"; it
//      is not wired as one, so the grid hairline goes near-invisible
//      (dark-ink line on a near-black `#1a1a1a` surface) in dark mode.
//   2. `KeyboardShortcutsDialog.tsx`'s row/kbd borders — a component built
//      entirely within this feature (T063), same bug: literal instead of
//      token, so table-row dividers and key-cap borders go near-invisible
//      on the dark dialog surface.
//
// See this task's (T061) summary for the flag — fixing these two lines is
// out of scope for T061 itself (implementation belongs to whichever task
// owns each file: US2's chart restyle, US5's dialog).
// ---------------------------------------------------------------------------

function readSource(relativePath: string): string {
  return readFileSync(path.resolve(process.cwd(), relativePath), "utf-8");
}

describe("T061 — dark-on-dark invisible-mark static sweep", () => {
  it("DistributionChart's CartesianGrid uses the border-gray TOKEN, not the light-mode-only literal", () => {
    const source = readSource("src/components/athletes/ai/DistributionChart.tsx");
    const gridLine = source
      .split("\n")
      .find((line) => line.includes("<CartesianGrid"));
    expect(gridLine).toBeDefined();
    expect(gridLine).not.toContain("rgba(34,42,53,0.08)");
    expect(gridLine).toMatch(/var\(--color-border-gray\)/);
  });

  it("EvolutionChart's CartesianGrid uses the border-gray TOKEN, not the light-mode-only literal", () => {
    const source = readSource("src/components/athletes/ai/EvolutionChart.tsx");
    const gridLine = source
      .split("\n")
      .find((line) => line.includes("<CartesianGrid"));
    expect(gridLine).toBeDefined();
    expect(gridLine).not.toContain("rgba(34,42,53,0.08)");
    expect(gridLine).toMatch(/var\(--color-border-gray\)/);
  });

  it("KeyboardShortcutsDialog's row/kbd borders use the border-gray TOKEN, not a hardcoded literal", () => {
    const source = readSource("src/components/layout/KeyboardShortcutsDialog.tsx");
    expect(source).not.toMatch(/border-\[rgba\(34,42,53,0\.(08|15)\)\]/);
  });
});
