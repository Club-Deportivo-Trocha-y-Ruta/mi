/**
 * statusConsistency.crossModule — regresión transversal (T025, feature 033)
 * que fija en un test el "spec.md §User Story 1, Acceptance Scenario 3":
 *
 *   "Given the same state shown in two modules (e.g., 'outdated' for an
 *    analysis and for a consent), When compared, Then the presentation is
 *    identical in color, shape, and wording convention."
 *
 * Los dos casos concretos del contrato (`status-vocabulary-sweep.md` §6/§7)
 * son:
 *   - ConsentStatusPanel's "outdated" consent → warning/"Desactualizado"
 *   - StaleAnalysisBadge's "stale" analysis   → warning/"Análisis desactualizado"
 *
 * Ambos son variantes del mismo concepto ("esto ya no refleja el estado
 * actual") en dos dominios distintos. Este test monta AMBOS componentes
 * reales (no solo compara los adaptadores puros) y verifica que el
 * `StatusBadge` resultante es idéntico en color/forma/posición del ícono —
 * y difiere ÚNICAMENTE en el texto del label.
 */
import { describe, it, expect, vi } from "vitest";
import { createElement } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/hooks/consent", () => ({
  useRenewConsent: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useWithdrawConsent: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/hooks/ai/useRaceRun", () => ({
  useReExecuteRun: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { ConsentStatusPanel, consentStatus } from "@/components/consent/ConsentStatusPanel";
import { StaleAnalysisBadge, staleAnalysisStatus } from "@/components/competitions/insights/StaleAnalysisBadge";
import type { AthleteConsentStatus, PrivacyPolicySummary } from "@/types/consent";

function makeWrapper() {
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

// current_consent.is_current_policy=false → getConsentState() resuelve "outdated".
const outdatedAthlete: AthleteConsentStatus = {
  athlete_id: 1,
  athlete_name: "Atleta Desactualizado",
  current_consent: {
    id: 10,
    policy_version: "v1.1",
    consented_at: "2026-04-01T09:00:00Z",
    is_current_policy: false,
    withdrawn_at: null,
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: false,
      third_party_sharing: false,
    },
  },
};

/** Recorre el `<span>` de StatusBadge devolviendo su firma visual — clases
 * de color/forma + nombre del componente de ícono lucide — sin el texto. */
function badgeSignature(badgeSpan: Element | null) {
  if (!badgeSpan) throw new Error("badge span not found");
  const icon = badgeSpan.querySelector("svg");
  return {
    // Clases del pill (color/forma) — el texto va en un nodo hijo aparte,
    // así que las classNames del <span> en sí son puramente presentacionales.
    pillClassName: badgeSpan.className,
    // El ícono debe ser el mismo componente lucide (misma clase generada
    // por lucide-react, ej. "lucide-triangle-alert" para AlertTriangle).
    iconClassName: icon?.getAttribute("class"),
    iconAriaHidden: icon?.getAttribute("aria-hidden"),
    // Posición: el ícono debe ser el primer hijo (antes del texto del label),
    // igual en ambos dominios.
    iconIsFirstChild: badgeSpan.firstElementChild === icon,
  };
}

describe("Cross-module consistency — 'outdated' (consent) vs 'stale' (analysis)", () => {
  it("los adaptadores puros mapean ambos a status=warning, con labels distintos", () => {
    const outdated = consentStatus("outdated");
    const stale = staleAnalysisStatus();

    expect(outdated.status).toBe("warning");
    expect(stale.status).toBe("warning");

    // Difieren SOLO en el texto — ese es el punto del escenario 3 de spec.md.
    expect(outdated.label).toBe("Desactualizado");
    expect(stale.label).toBe("Análisis desactualizado");
    expect(outdated.label).not.toBe(stale.label);
  });

  it("los StatusBadge renderizados por ambos componentes reales son idénticos en color/forma/posición del ícono", async () => {
    // --- Consent: monta ConsentStatusPanel con un atleta en estado "outdated" ---
    render(
      <ConsentStatusPanel
        consentsPerAthlete={[outdatedAthlete]}
        activePolicy={activePolicy}
      />,
      { wrapper: makeWrapper() },
    );
    fireEvent.click(screen.getByRole("button", { name: /Gestionar consentimiento/i }));
    const consentBadgeSpan = screen.getByText("Desactualizado").closest("span");

    // --- Analysis: monta StaleAnalysisBadge (único estado, "stale") ---
    render(<StaleAnalysisBadge runId="run-abc" />);
    const staleBadgeSpan = screen.getByText("Análisis desactualizado").closest("span");

    const consentSig = badgeSignature(consentBadgeSpan);
    const staleSig = badgeSignature(staleBadgeSpan);

    // Color + forma (className del pill) idénticos — mismo token `warning`.
    expect(consentSig.pillClassName).toBe(staleSig.pillClassName);

    // Mismo ícono (AlertTriangle es el default de status="warning" para
    // ambos adaptadores — ninguno pasa un `icon` override).
    expect(consentSig.iconClassName).toBe(staleSig.iconClassName);
    expect(consentSig.iconAriaHidden).toBe("true");
    expect(staleSig.iconAriaHidden).toBe("true");

    // Mismo posicionamiento: ícono siempre antes del texto del label.
    expect(consentSig.iconIsFirstChild).toBe(true);
    expect(staleSig.iconIsFirstChild).toBe(true);

    // La única diferencia visible entre ambos: el texto del label.
    expect(consentBadgeSpan?.textContent).toBe("Desactualizado");
    expect(staleBadgeSpan?.textContent).toBe("Análisis desactualizado");
    expect(consentBadgeSpan?.textContent).not.toBe(staleBadgeSpan?.textContent);
  });
});
