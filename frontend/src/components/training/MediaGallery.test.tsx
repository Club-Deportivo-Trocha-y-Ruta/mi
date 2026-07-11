/**
 * Tests para MediaGallery — guard de borrado de media (foto/video):
 *  - Regresión: el guard ya NO usa window.confirm() — se reemplazó por
 *    ConfirmDialog (tone="danger"). Un spy sobre window.confirm debe
 *    quedar en cero llamadas en todos los flujos (abrir, confirmar,
 *    cancelar).
 *  - ConfirmDialog gatea la eliminación: onDelete solo se invoca tras
 *    click en "Borrar" dentro del diálogo — nunca al abrir el diálogo,
 *    nunca al cancelar.
 *  - a11y: jest-axe sin violaciones con el diálogo cerrado y abierto.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { MediaGallery } from "./MediaGallery";
import type { SessionMedia } from "@/types/trainingSession.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMedia(overrides: Partial<SessionMedia> = {}): SessionMedia {
  return {
    id: 1,
    session_id: 10,
    media_type: "photo",
    storage_url: "https://cdn.example.com/photo1.jpg",
    thumbnail_url: "https://cdn.example.com/photo1-thumb.jpg",
    filename_original: "photo1.jpg",
    mime_type: "image/jpeg",
    size_bytes: 1024,
    width: 800,
    height: 600,
    duration_sec: null,
    caption: "Sesión de técnica",
    consent_ack: true,
    uploaded_by_user_id: 5,
    uploaded_at: "2026-07-01T10:00:00Z",
    athlete_ids: [1, 2],
    ...overrides,
  };
}

/** Abre el lightbox haciendo click en la miniatura y luego en "Borrar". */
async function openLightboxAndClickDelete(
  user: ReturnType<typeof userEvent.setup>,
  mediaId = 1,
) {
  await user.click(screen.getByTestId(`media-thumb-${mediaId}`));
  await user.click(await screen.findByTestId("media-delete-button"));
}

describe("MediaGallery — guard de borrado", () => {
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Si el componente todavía llamara a window.confirm, esto lo detecta
    // (además de dejar en evidencia la llamada vía confirmSpy).
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    confirmSpy.mockRestore();
  });

  it("[regresión] nunca llama a window.confirm — abre ConfirmDialog en su lugar y gatea onDelete", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(<MediaGallery media={[makeMedia({ id: 7 })]} onDelete={onDelete} />);

    await openLightboxAndClickDelete(user, 7);

    // ConfirmDialog renderiza (AlertDialog de Radix -> role="alertdialog").
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toBeInTheDocument();

    // window.confirm nunca se invoca en ningún punto del flujo.
    expect(confirmSpy).not.toHaveBeenCalled();

    // onDelete no se dispara solo por abrir el diálogo.
    expect(onDelete).not.toHaveBeenCalled();

    // Confirmar dentro del diálogo es lo único que dispara onDelete.
    await user.click(within(dialog).getByRole("button", { name: "Borrar" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith(7);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("muestra title/description/tone danger del ConfirmDialog", async () => {
    const user = userEvent.setup();
    render(<MediaGallery media={[makeMedia()]} onDelete={vi.fn()} />);

    await openLightboxAndClickDelete(user);

    const dialog = await screen.findByRole("alertdialog");
    expect(
      within(dialog).getByRole("heading", { name: "¿Borrar esta media?" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Se eliminará para padres y entrenador/i),
    ).toBeInTheDocument();
    // tone="danger": foco inicial en Cancelar, nunca en Borrar.
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toHaveFocus();
  });

  it("cancelar cierra el ConfirmDialog sin llamar a onDelete y mantiene el lightbox abierto", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(<MediaGallery media={[makeMedia()]} onDelete={onDelete} />);

    await openLightboxAndClickDelete(user);
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();
    // El lightbox de la media sigue abierto tras cancelar.
    expect(screen.getByTestId("media-lightbox")).toBeInTheDocument();
  });

  it("confirmar cierra tanto el ConfirmDialog como el lightbox", async () => {
    const user = userEvent.setup();
    render(<MediaGallery media={[makeMedia()]} onDelete={vi.fn()} />);

    await openLightboxAndClickDelete(user);
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Borrar" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.queryByTestId("media-lightbox")).not.toBeInTheDocument();
  });

  it("no ofrece el guard de borrado en modo readOnly", async () => {
    const user = userEvent.setup();
    render(<MediaGallery media={[makeMedia()]} onDelete={vi.fn()} readOnly />);

    await user.click(screen.getByTestId("media-thumb-1"));

    expect(screen.queryByTestId("media-delete-button")).not.toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("deshabilita el botón de Borrar mientras isDeleting=true (evita doble disparo)", async () => {
    const user = userEvent.setup();
    render(<MediaGallery media={[makeMedia()]} onDelete={vi.fn()} isDeleting />);

    await user.click(screen.getByTestId("media-thumb-1"));

    expect(screen.getByTestId("media-delete-button")).toBeDisabled();
  });

  describe("accesibilidad", () => {
    it("sin violaciones con la grilla renderizada", async () => {
      const { container } = render(
        <MediaGallery media={[makeMedia()]} onDelete={vi.fn()} />,
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones con el ConfirmDialog abierto", async () => {
      const user = userEvent.setup();
      render(<MediaGallery media={[makeMedia()]} onDelete={vi.fn()} />);

      await openLightboxAndClickDelete(user);
      await screen.findByRole("alertdialog");

      // AlertDialog de Radix monta su contenido en un portal bajo
      // document.body (fuera del `container` de render()), igual que en
      // components/shared/__tests__/ConfirmDialog.test.tsx.
      expect(await axe(document.body)).toHaveNoViolations();
    });
  });
});
