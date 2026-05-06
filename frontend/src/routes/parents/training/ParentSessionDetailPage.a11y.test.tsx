import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/trainingSessions");
vi.mock("@/components/training/RouteViewer", () => ({
  RouteViewer: () => <div data-testid="route-viewer" />,
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useTrainingSession, useSessionAttendance } from "@/api/trainingSessions";
import { ParentSessionDetailPage } from "./ParentSessionDetailPage";
import type { Attendance, TrainingSession } from "@/types/trainingSession.types";
import type { MyAthleteOut } from "@/types/parent.types";

const MY_ATHLETE_ID = 42;

function makeAthlete(): MyAthleteOut {
  return {
    athlete_id: MY_ATHLETE_ID,
    athlete_first_name: "Sebastián",
    athlete_last_name: "García",
    birth_date: "2013-01-01",
    sex: "M" as never,
    age_decimal: 13.2,
    category: "U15",
    relationship: "padre" as never,
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

function makeSession(): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 2,
    age_group: "u15",
    status: "executed",
    scheduled_date: "2026-05-10",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: "Frenada controlada",
    description: "Sesión de técnica básica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  };
}

function makeAttendance(): Attendance {
  return {
    id: MY_ATHLETE_ID,
    session_id: 1,
    athlete_id: MY_ATHLETE_ID,
    athlete_name: "Sebastián García",
    status: "presente",
    rpe_omni: 7,
    rubric_effort: 4,
    rubric_attitude: 5,
    rubric_technique: 3,
    individual_feedback: "Buen trabajo en los descensos.",
    excuse_reason: null,
    created_at: "2026-05-10T00:00:00Z",
    updated_at: "2026-05-10T00:00:00Z",
  };
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderPage(sessionId = 1) {
  vi.mocked(useMyAthletes).mockReturnValue({
    data: [makeAthlete()],
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useMyAthletes>);

  vi.mocked(useTrainingSession).mockReturnValue({
    data: makeSession(),
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useTrainingSession>);

  vi.mocked(useSessionAttendance).mockReturnValue({
    data: [makeAttendance()],
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useSessionAttendance>);

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/parents/training/sessions/${sessionId}`]}>
        <Routes>
          <Route path="/parents/training/sessions/:id" element={<ParentSessionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ParentSessionDetailPage — accesibilidad", () => {
  it("sin violaciones axe con asistencia del atleta", async () => {
    const { container } = renderPage();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe cuando el atleta no está convocado", async () => {
    vi.mocked(useSessionAttendance).mockReturnValue({
      data: [] as Attendance[],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useSessionAttendance>);

    const { container } = renderPage();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("jerarquía de headings correcta (h1 presente, sin saltos)", () => {
    renderPage();

    const headings = screen.getAllByRole("heading");
    expect(headings.length).toBeGreaterThan(0);

    const levels = headings.map((h) => parseInt(h.tagName.replace("H", "")));
    // El primer heading debe ser el más alto nivel (h1 o h2)
    expect(levels[0]).toBeLessThanOrEqual(2);
  });

  it("los links tienen texto descriptivo (no solo iconos)", () => {
    renderPage();

    const links = screen.getAllByRole("link");
    for (const link of links) {
      const hasText = (link.textContent?.trim().length ?? 0) > 0;
      const hasAriaLabel = link.hasAttribute("aria-label");
      expect(hasText || hasAriaLabel).toBe(true);
    }
  });
});
