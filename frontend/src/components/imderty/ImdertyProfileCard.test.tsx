/**
 * Tests de ImdertyProfileCard (feature 047, US2, T037).
 *
 * Cubre solo la orquestación del propio componente — carga, error/retry y
 * el árbol de hijos cuando el perfil llega — no la lógica interna de
 * `ImdertyProfileForm`, `PrimaryContactSelect` ni `SensitiveDataCard`, cada
 * uno con su propio archivo de tests. Los tres hijos se stubean vía
 * `vi.mock` para aislar el orquestador (mismo patrón que `StaffPage.test.tsx`
 * mockeando `useStaff`/`useSetStaffActive`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { ImdertyProfile } from "@/schemas/imderty";

const useImdertyProfileMock = vi.fn();
vi.mock("@/hooks/useImderty", () => ({
  useImdertyProfile: (athleteId: number) => useImdertyProfileMock(athleteId),
}));

vi.mock("@/components/imderty/ImdertyProfileForm", () => ({
  ImdertyProfileForm: ({ athleteId }: { athleteId: number }) => (
    <div data-testid="stub-profile-form">form:{athleteId}</div>
  ),
}));

vi.mock("@/components/imderty/PrimaryContactSelect", () => ({
  PrimaryContactSelect: ({ athleteId, guardians }: { athleteId: number; guardians: unknown[] }) => (
    <div data-testid="stub-primary-contact">
      contact:{athleteId}:{guardians.length}
    </div>
  ),
}));

vi.mock("@/components/imderty/SensitiveDataCard", () => ({
  SensitiveDataCard: ({
    athleteId,
    authorization,
  }: {
    athleteId: number;
    authorization: unknown;
  }) => (
    <div data-testid="stub-sensitive-card">
      sensitive:{athleteId}:{authorization ? "authorized" : "locked"}
    </div>
  ),
}));

import { ImdertyProfileCard } from "@/components/imderty/ImdertyProfileCard";

function makeProfile(overrides?: Partial<ImdertyProfile>): ImdertyProfile {
  return {
    athlete_id: 42,
    first_surname: "Ficticio",
    second_surname: "Prueba",
    surname_split: { confirmed: true, proposed_first: null, proposed_second: null },
    document_type: null,
    document_number: null,
    address: null,
    barrio: null,
    other_municipality: false,
    school: null,
    grade: null,
    eps: null,
    phone: null,
    guardians: [
      { user_id: 1, display_name: "Acudiente Ficticio", has_phone: true, is_primary_contact: true },
    ],
    effective_phone_source: null,
    sensitive: { authorization: null },
    ...overrides,
  };
}

function renderCard(athleteId = 42) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ImdertyProfileCard athleteId={athleteId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ImdertyProfileCard — carga", () => {
  it("muestra el skeleton mientras isLoading", () => {
    useImdertyProfileMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });

    renderCard();

    expect(screen.getByRole("status", { name: "Cargando perfil IMDERTY…" })).toBeInTheDocument();
    expect(screen.queryByTestId("stub-profile-form")).not.toBeInTheDocument();
  });
});

describe("ImdertyProfileCard — error", () => {
  it("muestra la alerta de error y reintenta con el botón", async () => {
    const refetch = vi.fn();
    useImdertyProfileMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch,
    });

    const user = userEvent.setup();
    renderCard();

    expect(screen.getByText("No se pudo cargar el perfil IMDERTY")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Reintentar/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe("ImdertyProfileCard — perfil cargado", () => {
  it("renderiza el formulario, el contacto principal y la tarjeta de datos sensibles", async () => {
    const profile = makeProfile();
    useImdertyProfileMock.mockReturnValue({
      data: profile,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderCard(42);

    await waitFor(() => {
      expect(screen.getByTestId("stub-profile-form")).toHaveTextContent("form:42");
    });
    expect(screen.getByTestId("stub-primary-contact")).toHaveTextContent("contact:42:1");
    expect(screen.getByTestId("stub-sensitive-card")).toHaveTextContent("sensitive:42:locked");
  });

  it("propaga una autorización activa a SensitiveDataCard", async () => {
    const profile = makeProfile({
      sensitive: {
        authorization: { id: 1, guardian_user_id: 1, authorized_on: "2026-01-01", active: true },
      },
    });
    useImdertyProfileMock.mockReturnValue({
      data: profile,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderCard(42);

    await waitFor(() => {
      expect(screen.getByTestId("stub-sensitive-card")).toHaveTextContent("authorized");
    });
  });
});

describe("ImdertyProfileCard — ancla #imderty-profile", () => {
  const loaded = () =>
    useImdertyProfileMock.mockReturnValue({
      data: makeProfile(),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("la tarjeta exterior lleva id=imderty-profile", async () => {
    loaded();
    const { container } = renderCard();
    await screen.findByTestId("stub-profile-form");
    const anchor = container.querySelector("#imderty-profile");
    expect(anchor).not.toBeNull();
    expect(anchor).toContainElement(screen.getByText("Perfil IMDERTY"));
  });

  it("se desplaza a la sección cuando la URL trae el hash, una vez cargado el perfil", async () => {
    window.history.replaceState(null, "", "/athletes/42#imderty-profile");
    const scroll = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scroll;
    try {
      loaded();
      renderCard();
      await screen.findByTestId("stub-profile-form");
      await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
      expect(scroll.mock.contexts[0]).toHaveAttribute("id", "imderty-profile");
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("no se desplaza sin el hash", async () => {
    const scroll = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scroll;
    try {
      loaded();
      renderCard();
      await screen.findByTestId("stub-profile-form");
      expect(scroll).not.toHaveBeenCalled();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
});

describe("ImdertyProfileCard — accesibilidad", () => {
  it("0 violaciones jest-axe con el error de carga (sin h5 bajo el h3)", async () => {
    useImdertyProfileMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });
    const { container } = renderCard();
    expect(container.querySelector("h5")).toBeNull();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe con el perfil cargado", async () => {
    useImdertyProfileMock.mockReturnValue({
      data: makeProfile(),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const { container } = renderCard();
    await screen.findByTestId("stub-profile-form");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
