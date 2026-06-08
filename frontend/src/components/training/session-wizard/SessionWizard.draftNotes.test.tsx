/**
 * SessionWizard AI draft-notes banner tests (Feature 006, analyze finding C3).
 *
 * Verifies the read-only "Sugerencia de la IA" rationale banner:
 *   - shown when draftNotes is provided,
 *   - hidden when draftNotes is null/undefined,
 *   - dismissible via "Entendido",
 *   - 0 a11y violations.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

// --- Mock heavy wizard dependencies ----------------------------------------
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

const DEFAULTS: TrainingSessionFormValues = {
  scheduled_date: "",
  scheduled_start_time: "",
  duration_min: 60,
  location: "",
  technical_focus: "",
  description: "",
  session_kind: "entrenamiento",
  objectives: "",
  route_text: "",
  strava_url: "",
  coach_notes: "",
  convocados_athlete_ids: [],
};

function renderWizard(draftNotes?: string | null) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <SessionWizard mode="create" defaultValues={DEFAULTS} draftNotes={draftNotes} />
    </QueryClientProvider>,
  );
}

describe("SessionWizard AI draft-notes banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the read-only rationale banner when draftNotes is provided", () => {
    renderWizard("Faltan ~12 días para una válida A: intensidad moderada.");
    const banner = screen.getByTestId("assistant-notes-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent("Sugerencia de la IA");
    expect(banner).toHaveTextContent("intensidad moderada");
  });

  it("does not render the banner when draftNotes is absent", () => {
    renderWizard(null);
    expect(screen.queryByTestId("assistant-notes-banner")).not.toBeInTheDocument();
  });

  it("dismisses the banner when 'Entendido' is clicked", () => {
    renderWizard("Sugerencia de prueba.");
    expect(screen.getByTestId("assistant-notes-banner")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Entendido" }));
    expect(screen.queryByTestId("assistant-notes-banner")).not.toBeInTheDocument();
  });

  it("has no accessibility violations with the banner shown", async () => {
    const { container } = renderWizard("Sugerencia accesible.");
    expect(await axe(container)).toHaveNoViolations();
  });
});
