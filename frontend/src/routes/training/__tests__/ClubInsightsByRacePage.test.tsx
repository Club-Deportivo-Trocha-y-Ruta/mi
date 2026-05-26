/**
 * Tests vitest — ClubInsightsByRacePage (Sprint 3).
 *
 * Cubre:
 *  - Renderiza header con race_event_label + total atletas.
 *  - Renderiza N cards.
 *  - Coach: ve nombres reales + confidence + excerpts.
 *  - Parent (item enmascarado athlete_id=0): nombre "[Atleta del club]",
 *    sin excerpt, no clickeable (opacity-60).
 *  - Click en card no-enmascarada navega al perfil del atleta.
 *  - Empty state cuando items=[].
 *  - Error state + botón "Reintentar".
 *  - Param inválido (NaN) muestra "Válida no válida".
 *
 * Privacidad Ley 1581:
 *  - Badge de confianza nunca aparece para item con confidence=null.
 *  - Card con athlete_id=0 tiene opacity-60 y no invoca navigate.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  clubInsightsByRaceDefaultResponse,
  emptyClubInsightsByRaceHandler,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { ClubInsightsByRacePage } from "@/routes/training/ClubInsightsByRacePage";

// Mock de react-router-dom — useParams + useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useParams: vi.fn(() => ({ raceEventId: "4" })),
    useNavigate: () => mockNavigate,
    Link: actual.Link,
  };
});

import { useParams } from "react-router-dom";

function renderPage() {
  return renderWithProviders(<ClubInsightsByRacePage />, {
    initialEntries: ["/training/races/4/club-insights"],
  });
}

describe("ClubInsightsByRacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useParams).mockReturnValue({ raceEventId: "4" });
  });

  it("renderiza header con race_event_label y total_athletes", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/Válida 4 — Cali 17 may 2026/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/3 atletas/i)).toBeInTheDocument();
  });

  it("renderiza N cards (3 items del handler default)", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId("club-insight-card-145"),
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId("club-insight-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("club-insight-card-201")).toBeInTheDocument();
  });

  it("coach ve nombre real + confidence + excerpt del atleta 145", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Isabel Quiñoez")).toBeInTheDocument();
    });
    // Confidence badge
    expect(screen.getByText(/Confianza media/i)).toBeInTheDocument();
    // Excerpt
    expect(
      screen.getByText(/Finalizó en 3er lugar/i),
    ).toBeInTheDocument();
  });

  it("item enmascarado (athlete_id=0) muestra '[Atleta del club]' sin excerpt y SIN confidence", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("club-insight-card-0")).toBeInTheDocument();
    });
    const maskedCard = screen.getByTestId("club-insight-card-0");
    expect(maskedCard).toHaveTextContent("[Atleta del club]");
    // Sin excerpt (confidence=null del backend)
    expect(maskedCard).not.toHaveTextContent("Confianza");
    // opacity-60 (no clickeable)
    expect(maskedCard).toHaveClass("opacity-60");
    // cursor-default
    expect(maskedCard).toHaveClass("cursor-default");
  });

  it("item sin insight_id (201) muestra badge 'Sin análisis'", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("club-insight-card-201")).toBeInTheDocument();
    });
    const card = screen.getByTestId("club-insight-card-201");
    expect(card).toHaveTextContent("Sin análisis");
    expect(card).toHaveTextContent("El análisis está pendiente");
  });

  it("click en card no-enmascarada (athlete_id=145) navega al perfil", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("club-insight-card-145")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("club-insight-card-145"));
    expect(mockNavigate).toHaveBeenCalledWith(
      "/athletes/145?tab=ai_analysis&insight=99",
    );
  });

  it("click en card enmascarada (athlete_id=0) NO navega", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("club-insight-card-0")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("club-insight-card-0"));
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("empty state cuando items=[]", async () => {
    mswServer.use(emptyClubInsightsByRaceHandler);
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/No hay atletas con resultados en esta válida/i),
      ).toBeInTheDocument();
    });
  });

  it("error state muestra botón Reintentar", async () => {
    mswServer.use(
      http.get(
        "*/api/races/:raceEventId/club-insights",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/No se pudo cargar la información/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Reintentar/i })).toBeInTheDocument();
  });

  it("param NaN muestra 'Válida no válida' y botón Volver", () => {
    vi.mocked(useParams).mockReturnValue({ raceEventId: "abc" });
    renderPage();
    expect(screen.getByText(/Válida no válida/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Volver/i }),
    ).toBeInTheDocument();
  });

  it("botón Volver invoca navigate(-1)", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/Válida 4 — Cali 17 may 2026/i),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Volver/i }));
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it("respeta el testid de la página", async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId("club-insights-by-race-page"),
      ).toBeInTheDocument();
    });
  });

  it("total_athletes = 1 usa singular 'atleta'", async () => {
    mswServer.use(
      http.get(
        "*/api/races/:raceEventId/club-insights",
        () =>
          HttpResponse.json({
            ...clubInsightsByRaceDefaultResponse,
            total_athletes: 1,
            items: [clubInsightsByRaceDefaultResponse.items[0]],
          }),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/1 atleta$/i)).toBeInTheDocument();
    });
  });
});
