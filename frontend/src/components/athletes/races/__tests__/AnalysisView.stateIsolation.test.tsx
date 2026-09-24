/**
 * T011 (feature 036, US3) — aislamiento de estado al cambiar de atleta.
 *
 * Feature 045 (T042): re-alojada desde
 * `AthleteAIAnalysisTab.stateIsolation.test.tsx` — el estado que se filtraba
 * (selección de insight, run activo y HITL) vive ahora en
 * `races/AnalysisView.tsx`, montada dentro de `CarrerasTab`. Ya no hay
 * sub-tabs: el formulario de lanzamiento, el timeline en vivo, el histórico
 * y la barra de boletín conviven en la misma vista.
 *
 * Reproduce el bug que arregla T010 (`key={athlete.id}` en
 * `frontend/src/routes/athletes/AthleteDetailPage.tsx`, hoy sobre
 * `CarrerasTab`): sin una key por atleta, la vista es la MISMA instancia de
 * React entre dos atletas — selección de insight, run activo y estado HITL de
 * uno se filtran al perfil del otro.
 *
 * Este archivo NO mockea ningún sub-componente: monta el árbol real
 * (PanoramaView, InsightsTimeline, LaunchAnalysisForm, AnalysisRunTimeline,
 * HITLApprovalCard). Sólo se mockea la red, vía MSW — mockear los
 * sub-componentes es justo lo que dejó pasar esta clase de bug.
 *
 * `AthleteTabHost` replica el punto de montaje real (incluida la key) un
 * nivel por debajo de la página/ruta, para ejercitar el árbol real sin la
 * carga de mockear todo lo que `AthleteDetailPage` trae consigo.
 *
 * La prueba de que la key en sí funciona A TRAVÉS de la página real
 * (`routes/athletes/AthleteDetailPage.test.tsx`, suite "T010
 * key={athlete.id}...") vive aparte: monta `AthleteDetailPage` de verdad y
 * navega entre dos atletas sin desmontar la página, confirmando el remount
 * con un espía de montaje en `CarrerasTab`.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import {
  racesListHandler,
  mockInsightDetail,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AnalysisView } from "@/components/athletes/races/AnalysisView";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";
import { aiStatusOkHandler, hitlWaitingRunStatusHandler } from "./raceRunTestHandlers";

const ATHLETE_A: AthleteOut = {
  id: 501,
  user_id: 900,
  first_name: "Atleta",
  last_name: "Uno",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

const ATHLETE_B: AthleteOut = {
  ...ATHLETE_A,
  id: 502,
  first_name: "Atleta",
  last_name: "Dos",
};

/** Espeja el mount real de `AthleteDetailPage.tsx` (T010) un nivel por
 * debajo de la página: la key por atleta vive acá, no en el componente bajo
 * prueba. */
function AthleteTabHost({ athlete }: { athlete: AthleteOut }) {
  return <AnalysisView key={athlete.id} athlete={athlete} audience="coach" />;
}

// Ids del handler global GET /insights (athleteRaceAnalysisHandlers.ts):
// mockInsight() por defecto trae id=1, el segundo item del listado id=2.
const A_INSIGHT_ID = 1;
const A_NEWSLETTER_INSIGHT_ID = 2;

describe("AnalysisView — T011 aislamiento de estado entre atletas", () => {
  let detailRequestedIds: number[];

  beforeEach(() => {
    detailRequestedIds = [];
    mswServer.use(
      racesListHandler,
      aiStatusOkHandler(),
      hitlWaitingRunStatusHandler(),
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) => {
          const insightId = Number(params.insightId);
          detailRequestedIds.push(insightId);
          return HttpResponse.json(mockInsightDetail({ id: insightId }));
        },
      ),
    );
  });

  it(
    "al cambiar de atleta (A → B) se resetea la selección de boletín, el run " +
      "activo y el HITL; ninguna request de detalle vuelve a pedir el insight " +
      "que estaba abierto para A",
    async () => {
      const user = userEvent.setup();
      const { rerender } = renderWithProviders(
        <AthleteTabHost athlete={ATHLETE_A} />,
      );

      // 1) Lanzar un análisis real desde "Analizar con IA" (LaunchAnalysisForm
      //    real, sin mock) para obtener un activeRunId real. Ya no hay
      //    sub-tab de lanzamiento: el formulario está al final de la vista.
      const eventChip = await screen.findByTestId("launch-event-91");
      await user.click(eventChip);
      await user.click(screen.getByTestId("launch-submit"));

      // El submit monta el timeline real (poll real vía MSW) + la HITL card
      // real a partir del evento hitl_request servido por el handler.
      await screen.findByTestId("analysis-run-timeline");
      await screen.findByTestId("hitl-approval-card");

      // 2) Seleccionar un insight para el boletín (multi-select real, BB4).
      const checkbox = await screen.findByTestId(
        `insight-checkbox-${A_NEWSLETTER_INSIGHT_ID}`,
      );
      await user.click(checkbox);
      await waitFor(() => {
        expect(screen.getByTestId("newsletter-action-bar")).toBeInTheDocument();
      });

      // 3) Abrir el detalle del insight de A (Sheet/Dialog real) — lo
      //    dejamos ABIERTO al cambiar de atleta, para reproducir la fuga
      //    tal cual ocurriría (no lo cerramos manualmente).
      await user.click(screen.getByTestId(`insight-card-${A_INSIGHT_ID}`));
      await waitFor(() => {
        expect(detailRequestedIds).toContain(A_INSIGHT_ID);
      });
      await screen.findByText(/detalle del análisis/i);

      detailRequestedIds.length = 0; // sólo nos importa lo que pase TRAS el switch

      // 4) Cambiar de atleta — el host real usa key={athlete.id} (T010),
      //    igual que AthleteDetailPage.tsx.
      rerender(<AthleteTabHost athlete={ATHLETE_B} />);

      // 5) Tras el remount: Panorama de B, sin timeline, sin HITL,
      //    sin selección de boletín y sin el detalle de A abierto.
      await screen.findByTestId("panorama-view");
      expect(
        screen.queryByTestId("analysis-run-timeline"),
      ).not.toBeInTheDocument();
      expect(screen.queryByTestId("hitl-approval-card")).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("newsletter-action-bar"),
      ).not.toBeInTheDocument();
      expect(screen.queryByText(/detalle del análisis/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

      // Ninguna request de detalle debe volver a pedir el insight de A de
      // forma automática (sin que el coach haya clicado nada para B).
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(detailRequestedIds).not.toContain(A_INSIGHT_ID);
    },
  );
});
