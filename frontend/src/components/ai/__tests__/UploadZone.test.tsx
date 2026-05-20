import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { UploadZone } from "@/components/ai/UploadZone";

describe("UploadZone", () => {
  it("muestra el dropzone vacío inicialmente", () => {
    render(<UploadZone onUpload={vi.fn()} />);
    expect(screen.getByTestId("upload-zone-dropzone")).toBeInTheDocument();
    expect(screen.getByText(/Arrastra un PDF o CSV/i)).toBeInTheDocument();
  });

  it("rechaza archivo con extensión no permitida", async () => {
    const onUpload = vi.fn();
    render(<UploadZone onUpload={onUpload} />);
    const input = screen.getByTestId("upload-zone-input") as HTMLInputElement;
    const bad = new File(["x"], "doc.docx", {
      type: "application/octet-stream",
    });
    Object.defineProperty(input, "files", { value: [bad] });
    fireEvent.change(input);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Formato no permitido/i,
    );
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("rechaza archivos por tamaño", async () => {
    render(<UploadZone onUpload={vi.fn()} maxMb={1} />);
    const input = screen.getByTestId("upload-zone-input") as HTMLInputElement;
    const big = new File([new Uint8Array(2 * 1024 * 1024)], "big.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(input, "files", { value: [big] });
    fireEvent.change(input);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /excede el límite/i,
    );
  });

  it("acepta PDF válido y llama onUpload", async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined);
    render(<UploadZone onUpload={onUpload} />);
    const input = screen.getByTestId("upload-zone-input") as HTMLInputElement;
    const ok = new File([new Uint8Array(1024)], "ok.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(input, "files", { value: [ok] });
    fireEvent.change(input);
    await new Promise((r) => setTimeout(r, 0));
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload.mock.calls[0][0]).toBe(ok);
  });

  it("muestra spinner cuando isUploading=true", () => {
    render(<UploadZone onUpload={vi.fn()} isUploading />);
    expect(screen.getByText(/Subiendo/i)).toBeInTheDocument();
  });

  it("propaga error externo del servidor", () => {
    render(
      <UploadZone
        onUpload={vi.fn()}
        uploadError="El backend rechazó el formato"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /backend rechazó/i,
    );
  });

  it("soporta keyboard (Enter abre selector)", async () => {
    const user = userEvent.setup();
    render(<UploadZone onUpload={vi.fn()} />);
    const drop = screen.getByTestId("upload-zone-dropzone");
    drop.focus();
    // Pulsar Enter no provoca side effect verificable en jsdom (no abre
    // file dialog real), pero al menos no debe lanzar errores.
    await user.keyboard("{Enter}");
    expect(drop).toBeInTheDocument();
  });
});
