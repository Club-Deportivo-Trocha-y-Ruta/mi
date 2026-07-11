/**
 * SessionWizard step-focus management regression test (feature 028, T050).
 *
 * Contract (documented in `@/components/shared/Stepper`): the host wizard
 * keeps a ref + `tabIndex={-1}` on its own step heading and a `useEffect`
 * keyed on the active step index that calls `ref.current?.focus()` on
 * change, so every SUCCESSFUL step transition announces the new heading to
 * screen readers. This is additive to — and must not interfere with — the
 * pre-existing validation-failure focus behavior (`trigger(fields, {
 * shouldFocus: true })` inside `goNext()`), which is exercised elsewhere
 * (e.g. `StepGeneral.test.tsx`) and is left untouched.
 *
 * Must fail on unfixed code: before this change `SessionWizard` rendered
 * `SessionStepper` with no step heading at all — no `wizard-step-heading`
 * element existed and nothing ever called `.focus()` on step change.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

// --- Mock heavy wizard dependencies (same scaffold as
// SessionWizard.draftNotes.test.tsx) ----------------------------------------
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

const noopMutation = { mutateAsync: vi.fn(), isPending: false, reset: vi.fn() };
vi.mock("@/api/trainingSessions", () => ({
  useCreateTrainingSession: () => noopMutation,
  useUpdateTrainingSession: () => noopMutation,
  bulkSetConvocatoria: vi.fn(),
  fetchTrainingSession: vi.fn(),
  uploadRouteFile: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ user: { id: 1 } }),
}));

vi.mock("@/hooks/useFormDraft", () => ({
  useFormDraft: () => ({
    restoreCandidate: null,
    saveDraft: vi.fn(),
    clearDraft: vi.fn(),
  }),
}));

import { SessionWizard } from "./SessionWizard";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

// Step 1 (STEP_GENERAL_FIELDS) is already valid so a single "Siguiente"
// click advances the wizard without needing to fill in the form first —
// keeps the test focused on the focus-management behavior, not on form
// filling (covered by StepGeneral.test.tsx).
const VALID_STEP1_DEFAULTS: TrainingSessionFormValues = {
  scheduled_date: "2026-08-01",
  scheduled_start_time: "16:00",
  duration_min: 60,
  location: "Pista XCO La Buitrera",
  technical_focus: "Frenada en descenso",
  description: "Sesión técnica de frenada y curvas.",
  session_kind: "entrenamiento",
  objectives: "",
  route_text: "",
  strava_url: "",
  coach_notes: "",
  convocados_athlete_ids: [],
};

function renderWizard() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <SessionWizard mode="create" defaultValues={VALID_STEP1_DEFAULTS} />
    </QueryClientProvider>,
  );
}

describe("SessionWizard step-focus management", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("moves focus to the new step's heading after a successful goNext()", async () => {
    const user = userEvent.setup();
    renderWizard();

    // Step 1 heading renders (and is focused by the mount-time effect run).
    expect(screen.getByTestId("wizard-step-heading")).toHaveTextContent("General");

    await user.click(screen.getByRole("button", { name: /Siguiente/i }));

    // goNext() validates STEP_GENERAL_FIELDS only; VALID_STEP1_DEFAULTS
    // already satisfies trainingSessionCreateSchema, so validation succeeds
    // and the wizard advances to step 2 ("Atletas").
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step-heading")).toHaveTextContent("Atletas"),
    );

    expect(screen.getByTestId("wizard-step-heading")).toHaveFocus();
  });

  it("has no accessibility violations after a successful step change", async () => {
    const user = userEvent.setup();
    const { container } = renderWizard();

    await user.click(screen.getByRole("button", { name: /Siguiente/i }));
    await waitFor(() =>
      expect(screen.getByTestId("wizard-step-heading")).toHaveTextContent("Atletas"),
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
