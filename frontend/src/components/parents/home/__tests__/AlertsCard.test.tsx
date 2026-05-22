import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { AlertsCard } from "@/components/parents/home/AlertsCard";
import type { AthleteConsentStatus, CurrentConsent } from "@/types/consent";

function consentOk(): CurrentConsent {
  return {
    id: 1,
    policy_version: "1.1",
    consented_at: "2026-05-01T00:00:00Z",
    is_current_policy: true,
    withdrawn_at: null,
    grants: {
      data_collection: true,
      anthropometry: true,
      training_tracking: true,
      third_party_sharing: false,
    },
  };
}

function mkAthleteConsent(
  athleteName: string,
  current: CurrentConsent | null,
): AthleteConsentStatus {
  return {
    athlete_id: 1,
    athlete_name: athleteName,
    current_consent: current,
  };
}

describe("AlertsCard", () => {
  it("no renderiza nada cuando isLoading", () => {
    const { container } = render(
      <AlertsCard consentsPerAthlete={undefined} isLoading={true} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("no renderiza nada cuando todos los consentimientos están al día", () => {
    const { container } = render(
      <AlertsCard
        consentsPerAthlete={[mkAthleteConsent("Santiago", consentOk())]}
        isLoading={false}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("muestra alerta 'missing' cuando current_consent es null", () => {
    render(
      <AlertsCard
        consentsPerAthlete={[mkAthleteConsent("Santiago", null)]}
        isLoading={false}
      />,
    );
    expect(screen.getByTestId("alerts-card")).toBeInTheDocument();
    expect(screen.getByText("Santiago:")).toBeInTheDocument();
    expect(
      screen.getByText(/Falta autorizar el tratamiento de datos/i),
    ).toBeInTheDocument();
  });

  it("muestra alerta 'outdated' cuando política desactualizada", () => {
    const outdated = { ...consentOk(), is_current_policy: false };
    render(
      <AlertsCard
        consentsPerAthlete={[mkAthleteConsent("Mateo", outdated)]}
        isLoading={false}
      />,
    );
    expect(
      screen.getByText(/La política de privacidad cambió/i),
    ).toBeInTheDocument();
  });

  it("muestra alerta 'withdrawn' cuando consentimiento revocado", () => {
    const withdrawn = { ...consentOk(), withdrawn_at: "2026-05-01T00:00:00Z" };
    render(
      <AlertsCard
        consentsPerAthlete={[mkAthleteConsent("Mateo", withdrawn)]}
        isLoading={false}
      />,
    );
    expect(screen.getByText(/Tu autorización fue revocada/i)).toBeInTheDocument();
  });

  it("agrupa múltiples atletas con problemas en la misma card", () => {
    render(
      <AlertsCard
        consentsPerAthlete={[
          mkAthleteConsent("Santiago", null),
          mkAthleteConsent("Mateo", { ...consentOk(), is_current_policy: false }),
        ]}
        isLoading={false}
      />,
    );
    expect(screen.getByText("Santiago:")).toBeInTheDocument();
    expect(screen.getByText("Mateo:")).toBeInTheDocument();
  });
});
