import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MediaUploadZone } from "./MediaUploadZone";

const ATHLETES = [
  { id: 1, label: "Sofía García" },
  { id: 2, label: "Mateo Rodríguez" },
];

describe("MediaUploadZone", () => {
  it("muestra el dropzone vacío inicialmente", () => {
    render(
      <MediaUploadZone athletes={ATHLETES} onUpload={vi.fn().mockResolvedValue({})} />,
    );
    expect(screen.getByTestId("media-upload-dropzone")).toBeInTheDocument();
  });

  it("rechaza archivos con extensión no permitida y muestra error", async () => {
    const onUpload = vi.fn();
    render(<MediaUploadZone athletes={ATHLETES} onUpload={onUpload} />);

    const input = screen.getByTestId("media-file-input") as HTMLInputElement;
    const badFile = new File(["x"], "doc.pdf", { type: "application/pdf" });
    Object.defineProperty(input, "files", { value: [badFile] });
    fireEvent.change(input);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Formato no permitido/i);
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("rechaza fotos de más de 10MB", async () => {
    render(<MediaUploadZone athletes={ATHLETES} onUpload={vi.fn()} />);
    const input = screen.getByTestId("media-file-input") as HTMLInputElement;
    const big = new File([new Uint8Array(11 * 1024 * 1024)], "big.jpg", {
      type: "image/jpeg",
    });
    Object.defineProperty(input, "files", { value: [big] });
    fireEvent.change(input);
    expect(await screen.findByRole("alert")).toHaveTextContent(/excede el límite/i);
  });

  it("acepta foto válida y deshabilita submit hasta marcar consentimiento + atleta", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn().mockResolvedValue({});
    render(<MediaUploadZone athletes={ATHLETES} onUpload={onUpload} />);

    const input = screen.getByTestId("media-file-input") as HTMLInputElement;
    const okFile = new File([new Uint8Array(1024)], "ok.jpg", {
      type: "image/jpeg",
    });
    Object.defineProperty(input, "files", { value: [okFile] });
    fireEvent.change(input);

    const submit = await screen.findByTestId("media-submit-button");
    expect(submit).toBeDisabled();

    // Marca atleta
    await user.click(screen.getByRole("button", { name: "Sofía García" }));
    expect(submit).toBeDisabled();

    // Marca consentimiento
    await user.click(screen.getByTestId("media-consent-checkbox"));
    expect(submit).toBeEnabled();

    await user.click(submit);
    expect(onUpload).toHaveBeenCalledTimes(1);
    const call = onUpload.mock.calls[0][0];
    expect(call.media_type).toBe("photo");
    expect(call.athlete_ids).toEqual([1]);
    expect(call.consent_ack).toBe(true);
  });

  it("permite quitar el archivo seleccionado", async () => {
    const user = userEvent.setup();
    render(<MediaUploadZone athletes={ATHLETES} onUpload={vi.fn()} />);

    const input = screen.getByTestId("media-file-input") as HTMLInputElement;
    const okFile = new File([new Uint8Array(100)], "ok.png", { type: "image/png" });
    Object.defineProperty(input, "files", { value: [okFile] });
    fireEvent.change(input);

    expect(await screen.findByTestId("media-upload-form")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /quitar archivo/i }));
    expect(screen.getByTestId("media-upload-dropzone")).toBeInTheDocument();
  });
});
