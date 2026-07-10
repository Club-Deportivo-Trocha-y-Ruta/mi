/**
 * Tests de ActivityEvidenceStrip (specs/025-strava-activity-sync/
 * session-detail-redesign.md §8).
 *
 * Cubre: los cuatro estados de render, el toggle del chevron (un solo
 * nivel de disclosure, sin acordeón anidado), la acción "Enlazar" gateada
 * por `canLink`, y los objetivos de touch target de 48px de los nuevos
 * controles.
 *
 * Nota: la comparación planeado-vs-actual (badge de color verde/ámbar/rojo)
 * que vivía aquí fue removida por decisión de producto (señal demasiado
 * ruidosa/dinámica por ahora) — sus tests se eliminaron junto con la
 * función que la calculaba.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { mockActivity } from "@/test/msw/stravaHandlers";
import { ActivityEvidenceStrip } from "./ActivityEvidenceStrip";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "coach" } }),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Estados de render
// ---------------------------------------------------------------------------

describe("ActivityEvidenceStrip — estados", () => {
  it("loading: muestra el skeleton", () => {
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[]}
        unlinkedActivities={[]}
        loading
        canLink
      />,
    );
    expect(screen.getByTestId("activity-evidence-loading-1")).toBeInTheDocument();
  });

  it("vacío: muestra 'Sin actividad Strava', sin badge ni botón", () => {
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[]}
        unlinkedActivities={[]}
        canLink
      />,
    );
    expect(screen.getByText(/Sin actividad Strava/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("sin enlazar: badge ámbar + duración/distancia + botón Enlazar (canLink=true)", () => {
    const activity = mockActivity({ id: 5, athlete_id: 1, link: null, elapsed_time_s: 3600, distance_m: 20000 });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[]}
        unlinkedActivities={[activity]}
        canLink
      />,
    );
    expect(screen.getByText(/Actividad sin enlazar/i)).toBeInTheDocument();
    expect(screen.getByText(/1 h.*20 km/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enlazar/i })).toBeInTheDocument();
  });

  it("sin enlazar: oculta el botón Enlazar por completo cuando canLink=false", () => {
    const activity = mockActivity({ id: 5, athlete_id: 1, link: null });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[]}
        unlinkedActivities={[activity]}
        canLink={false}
      />,
    );
    expect(screen.getByText(/Actividad sin enlazar/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enlazar/i })).not.toBeInTheDocument();
  });

  it("sin enlazar: con >1 actividad muestra el enlace '+N más — revisar en Actividades'", () => {
    const a1 = mockActivity({ id: 5, athlete_id: 1, link: null });
    const a2 = mockActivity({ id: 6, athlete_id: 1, link: null });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[]}
        unlinkedActivities={[a1, a2]}
        canLink
      />,
    );
    const link = screen.getByRole("link", { name: /\+1 más — revisar en Actividades/i });
    expect(link).toHaveAttribute("href", "/activities?athlete_id=1&linked=false");
  });

  it("enlazada: muestra duración/distancia/FC como texto informativo", () => {
    const activity = mockActivity({
      id: 5,
      athlete_id: 1,
      elapsed_time_s: 90 * 60,
      distance_m: 20000,
      average_heartrate: 140,
      link: { training_session_id: 10, session_label: "10 jul", linked_by: "Coach", linked_at: null },
    });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[activity]}
        unlinkedActivities={[]}
        canLink
      />,
    );
    expect(screen.getByText(/1 h 30 min.*20 km.*140 lpm/)).toBeInTheDocument();
  });

  it("enlazada: el chevron alterna 'expanded' y renderiza un ActivityCard por actividad", async () => {
    const user = userEvent.setup();
    const a1 = mockActivity({
      id: 5,
      athlete_id: 1,
      name: "Rodada A",
      elapsed_time_s: 5400,
      link: { training_session_id: 10, session_label: "10 jul", linked_by: "Coach", linked_at: null },
    });
    const a2 = mockActivity({
      id: 6,
      athlete_id: 1,
      name: "Rodada B",
      elapsed_time_s: 1000,
      link: { training_session_id: 10, session_label: "10 jul", linked_by: "Coach", linked_at: null },
    });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[a1, a2]}
        unlinkedActivities={[]}
        canLink
      />,
    );

    const chevron = screen.getByRole("button", { name: /ver detalle de actividad/i });
    expect(chevron).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Rodada A")).not.toBeInTheDocument();

    await user.click(chevron);

    expect(chevron).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Rodada A")).toBeInTheDocument();
    expect(screen.getByText("Rodada B")).toBeInTheDocument();
    // Un solo nivel de disclosure: no debe haber un <details>/acordeón
    // anidado dentro del panel expandido.
    expect(document.querySelectorAll("details").length).toBe(0);
  });

  it("desempate: con >1 actividad enlazada, la de mayor elapsed_time_s es la 'primaria' del resumen colapsado", () => {
    const short = mockActivity({
      id: 5,
      athlete_id: 1,
      elapsed_time_s: 1000,
      distance_m: 5000,
      link: { training_session_id: 10, session_label: "10 jul", linked_by: "Coach", linked_at: null },
    });
    const long = mockActivity({
      id: 6,
      athlete_id: 1,
      elapsed_time_s: 90 * 60,
      distance_m: 20000,
      link: { training_session_id: 10, session_label: "10 jul", linked_by: "Coach", linked_at: null },
    });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[short, long]}
        unlinkedActivities={[]}
        canLink
      />,
    );
    // La compacta usa la actividad "long" (90 min, 20 km), no la de 1000 s.
    expect(screen.getByText(/1 h 30 min.*20 km/)).toBeInTheDocument();
    expect(screen.getByText(/\+1$/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Touch targets (48px floor)
// ---------------------------------------------------------------------------

describe("ActivityEvidenceStrip — touch targets 48px", () => {
  it("el botón Enlazar usa la clase h-12 (48px)", () => {
    const activity = mockActivity({ id: 5, athlete_id: 1, link: null });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[]}
        unlinkedActivities={[activity]}
        canLink
      />,
    );
    expect(screen.getByRole("button", { name: /Enlazar/i })).toHaveClass("h-12");
  });

  it("el chevron usa la clase h-12 w-12 (48px)", () => {
    const activity = mockActivity({
      id: 5,
      athlete_id: 1,
      link: { training_session_id: 10, session_label: "10 jul", linked_by: "Coach", linked_at: null },
    });
    wrap(
      <ActivityEvidenceStrip
        athleteId={1}
        linkedActivities={[activity]}
        unlinkedActivities={[]}
        canLink
      />,
    );
    const chevron = screen.getByRole("button", { name: /ver detalle de actividad/i });
    expect(chevron).toHaveClass("h-12", "w-12");
  });
});
