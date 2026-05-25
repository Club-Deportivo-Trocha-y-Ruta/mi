/**
 * Tests para AthleteNewsletterDetailPage.
 *
 * Cubre: botón Regenerar narrativa (draft/failed visible, approved/sent oculto),
 * botón Aprobar (draft visible), botón Enviar (approved habilitado).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/athleteNewsletters", () => ({
  useAthleteNewsletter: vi.fn(),
  useApproveNewsletter: vi.fn(),
  useSendNewsletter: vi.fn(),
  usePatchNewsletter: vi.fn(),
  useGenerateNewsletter: vi.fn(),
  useDownloadNewsletterPdf: vi.fn(),
  parseApiError: vi.fn((_err: unknown, fallback: string) => fallback),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1], id: 10 },
    }),
  ),
}));

vi.mock("@/components/training/NewsletterNarrativeEditor", () => ({
  NewsletterNarrativeEditor: () => <div data-testid="narrative-editor">Editor</div>,
}));

vi.mock("@/components/training/NewsletterPreviewBlocks", () => ({
  NewsletterPreviewBlocks: () => <div data-testid="preview-blocks">Preview</div>,
}));

import {
  useAthleteNewsletter,
  useApproveNewsletter,
  useSendNewsletter,
  usePatchNewsletter,
  useGenerateNewsletter,
  useDownloadNewsletterPdf,
} from "@/api/athleteNewsletters";
import { AthleteNewsletterDetailPage } from "./AthleteNewsletterDetailPage";
import { makeNewsletter } from "@/test/msw/newsletterHandlers";
import type { NewsletterStatus } from "@/types/athleteNewsletter.types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mutationStub = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  data: undefined,
  error: null,
  reset: vi.fn(),
};

function renderPage(athleteId = 42, newsletterId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter
        initialEntries={[`/training/athlete-newsletters/${athleteId}/${newsletterId}`]}
      >
        <Routes>
          <Route
            path="/training/athlete-newsletters/:athleteId/:newsletterId"
            element={<AthleteNewsletterDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function setupMocks(status: NewsletterStatus) {
  const newsletter = makeNewsletter({ status, athlete_id: 42, year: 2026, month: 5 });
  vi.mocked(useAthleteNewsletter).mockReturnValue({
    isLoading: false,
    isError: false,
    data: newsletter,
  } as unknown as ReturnType<typeof useAthleteNewsletter>);
  vi.mocked(useApproveNewsletter).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useApproveNewsletter>,
  );
  vi.mocked(useSendNewsletter).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useSendNewsletter>,
  );
  vi.mocked(usePatchNewsletter).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof usePatchNewsletter>,
  );
  vi.mocked(useGenerateNewsletter).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useGenerateNewsletter>,
  );
  vi.mocked(useDownloadNewsletterPdf).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useDownloadNewsletterPdf>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests: botón Regenerar narrativa
// ---------------------------------------------------------------------------

describe("AthleteNewsletterDetailPage — botón Regenerar narrativa", () => {
  it("muestra botón 'Regenerar narrativa' cuando el estado es draft", () => {
    setupMocks("draft");
    renderPage();
    expect(screen.getByTestId("regenerate-narrative-btn")).toBeInTheDocument();
  });

  it("NO muestra botón 'Regenerar narrativa' cuando el estado es approved", () => {
    setupMocks("approved");
    renderPage();
    expect(screen.queryByTestId("regenerate-narrative-btn")).not.toBeInTheDocument();
  });

  it("NO muestra botón 'Regenerar narrativa' cuando el estado es sent", () => {
    setupMocks("sent");
    renderPage();
    expect(screen.queryByTestId("regenerate-narrative-btn")).not.toBeInTheDocument();
  });

  it("NO muestra botón 'Regenerar narrativa' cuando el estado es failed (usa banner de error)", () => {
    setupMocks("failed");
    renderPage();
    expect(screen.queryByTestId("regenerate-narrative-btn")).not.toBeInTheDocument();
  });

  it("muestra ConfirmModal al hacer click en Regenerar narrativa (draft)", async () => {
    setupMocks("draft");
    renderPage();

    fireEvent.click(screen.getByTestId("regenerate-narrative-btn"));

    await waitFor(() => {
      expect(screen.getByText(/Se borrará la narrativa actual/i)).toBeInTheDocument();
    });
  });

  it("llama a generateMutation.mutate con force:true al confirmar regeneración", async () => {
    const mutateMock = vi.fn();
    setupMocks("draft");
    vi.mocked(useGenerateNewsletter).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useGenerateNewsletter>);

    renderPage();
    fireEvent.click(screen.getByTestId("regenerate-narrative-btn"));

    await waitFor(() =>
      screen.getByText(/Se borrará la narrativa actual/i),
    );

    // Confirmar en el modal
    fireEvent.click(screen.getByRole("button", { name: /Sí, regenerar/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({ force: true }),
      expect.any(Object),
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: botón Regenerar en banner de error (failed)
// ---------------------------------------------------------------------------

describe("AthleteNewsletterDetailPage — banner de error con botón Regenerar", () => {
  it("muestra el banner de error y botón Regenerar cuando estado es failed", () => {
    const newsletter = makeNewsletter({
      status: "failed",
      athlete_id: 42,
      year: 2026,
      month: 5,
      error_message: "Timeout al generar narrativa IA",
    });
    vi.mocked(useAthleteNewsletter).mockReturnValue({
      isLoading: false,
      isError: false,
      data: newsletter,
    } as unknown as ReturnType<typeof useAthleteNewsletter>);
    vi.mocked(useApproveNewsletter).mockReturnValue(mutationStub as any);
    vi.mocked(useSendNewsletter).mockReturnValue(mutationStub as any);
    vi.mocked(usePatchNewsletter).mockReturnValue(mutationStub as any);
    vi.mocked(useGenerateNewsletter).mockReturnValue(mutationStub as any);
    vi.mocked(useDownloadNewsletterPdf).mockReturnValue(mutationStub as any);

    renderPage();

    expect(screen.getByTestId("error-message-banner")).toBeInTheDocument();
    expect(screen.getByTestId("regenerate-btn")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: flujo aprobación y envío por estado
// ---------------------------------------------------------------------------

describe("AthleteNewsletterDetailPage — acciones por estado", () => {
  it("muestra botón Aprobar en estado draft", () => {
    setupMocks("draft");
    renderPage();
    expect(screen.getByTestId("approve-btn")).toBeInTheDocument();
  });

  it("NO muestra botón Aprobar en estado approved", () => {
    setupMocks("approved");
    renderPage();
    expect(screen.queryByTestId("approve-btn")).not.toBeInTheDocument();
  });

  it("botón Enviar habilitado en estado approved", () => {
    setupMocks("approved");
    renderPage();
    const sendBtn = screen.getByTestId("send-btn");
    expect(sendBtn).not.toBeDisabled();
  });

  it("botón Enviar deshabilitado en estado draft", () => {
    setupMocks("draft");
    renderPage();
    const sendBtn = screen.getByTestId("send-btn");
    expect(sendBtn).toBeDisabled();
  });
});
