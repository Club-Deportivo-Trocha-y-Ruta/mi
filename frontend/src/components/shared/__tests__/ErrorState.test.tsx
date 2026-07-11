import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { ErrorState, isColdStartError } from "../ErrorState";

describe("ErrorState", () => {
  // -------------------------------------------------------------------------
  // Mensaje por defecto
  // -------------------------------------------------------------------------
  describe("mensaje por defecto", () => {
    it("renderiza el mensaje por defecto cuando no se pasa message ni isColdStart", () => {
      render(<ErrorState />);
      expect(screen.getByText("No se pudo cargar la información.")).toBeInTheDocument();
    });

    it("renderiza el bloque con role=alert (no cold start)", () => {
      render(<ErrorState />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Mensaje personalizado
  // -------------------------------------------------------------------------
  describe("mensaje personalizado", () => {
    it("renderiza el message recibido en vez del mensaje por defecto", () => {
      render(<ErrorState message="No se pudo cargar el catálogo de ejercicios." />);
      expect(
        screen.getByText("No se pudo cargar el catálogo de ejercicios."),
      ).toBeInTheDocument();
      expect(screen.queryByText("No se pudo cargar la información.")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Variante cold start
  // -------------------------------------------------------------------------
  describe("variante cold start", () => {
    it("renderiza copy de arranque amigable por defecto", () => {
      render(<ErrorState isColdStart />);
      expect(
        screen.getByText(/La aplicación está iniciando/),
      ).toBeInTheDocument();
    });

    it("usa role=status (no alert) y tono cálido (ámbar), no rojo de error", () => {
      render(<ErrorState isColdStart />);
      const status = screen.getByRole("status");
      expect(status).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(status.className).toContain("warning");
      expect(status.className).not.toContain("danger");
    });

    it("respeta un message personalizado incluso en modo cold start", () => {
      render(<ErrorState isColdStart message="Cargando de nuevo, casi listo…" />);
      expect(screen.getByText("Cargando de nuevo, casi listo…")).toBeInTheDocument();
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Botón "Reintentar"
  // -------------------------------------------------------------------------
  describe("botón Reintentar", () => {
    it("no renderiza el botón cuando no se pasa onRetry", () => {
      render(<ErrorState />);
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("renderiza el botón Reintentar cuando se pasa onRetry", () => {
      render(<ErrorState onRetry={() => {}} />);
      expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    });

    it("llama a onRetry al hacer clic (callback síncrono)", async () => {
      const user = userEvent.setup();
      const onRetry = vi.fn();
      render(<ErrorState onRetry={onRetry} />);

      await user.click(screen.getByRole("button", { name: "Reintentar" }));

      expect(onRetry).toHaveBeenCalledTimes(1);
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Reintentar" })).not.toBeDisabled(),
      );
    });

    it("muestra un estado pendiente (deshabilitado + spinner) mientras onRetry async no resuelve, y lo limpia al resolver", async () => {
      const user = userEvent.setup();
      let resolveRetry: () => void = () => {};
      const onRetry = vi.fn(
        () =>
          new Promise<void>((resolve) => {
            resolveRetry = resolve;
          }),
      );

      render(<ErrorState onRetry={onRetry} />);
      const button = screen.getByRole("button", { name: "Reintentar" });

      await user.click(button);

      expect(onRetry).toHaveBeenCalledTimes(1);
      expect(button).toBeDisabled();
      // El ícono de espera (Loader2 con animate-spin) reemplaza al ícono estático.
      expect(button.querySelector("svg.animate-spin")).toBeInTheDocument();

      resolveRetry();

      await waitFor(() => expect(button).not.toBeDisabled());
      expect(button.querySelector("svg.animate-spin")).not.toBeInTheDocument();
    });

    it("ignora clics repetidos mientras ya está reintentando", async () => {
      const user = userEvent.setup();
      let resolveRetry: () => void = () => {};
      const onRetry = vi.fn(
        () =>
          new Promise<void>((resolve) => {
            resolveRetry = resolve;
          }),
      );

      render(<ErrorState onRetry={onRetry} />);
      const button = screen.getByRole("button", { name: "Reintentar" });

      await user.click(button);
      await user.click(button); // botón ya disabled — no debería disparar una segunda llamada

      expect(onRetry).toHaveBeenCalledTimes(1);
      resolveRetry();
      await waitFor(() => expect(button).not.toBeDisabled());
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad (jest-axe) — las tres variantes del contrato + retry
  // -------------------------------------------------------------------------
  describe("accesibilidad", () => {
    it("no introduce violaciones con el mensaje por defecto", async () => {
      const { container } = render(<ErrorState />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no introduce violaciones con un mensaje personalizado", async () => {
      const { container } = render(<ErrorState message="Algo salió mal al cargar los atletas." />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no introduce violaciones en la variante cold start", async () => {
      const { container } = render(<ErrorState isColdStart />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no introduce violaciones con el botón Reintentar presente", async () => {
      const { container } = render(<ErrorState onRetry={() => {}} />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});

describe("isColdStartError", () => {
  // -------------------------------------------------------------------------
  // Por texto del mensaje (case-insensitive)
  // -------------------------------------------------------------------------
  describe("por texto del mensaje", () => {
    it.each([
      ["timeout", new Error("Timeout of 5000ms exceeded")],
      ["network", new Error("Network Error")],
      ["503", new Error("Request failed with status code 503")],
      ["502", new Error("Request failed with status code 502")],
    ])("detecta cold start cuando el mensaje contiene %s (sin importar mayúsculas)", (_label, err) => {
      expect(isColdStartError(err)).toBe(true);
    });

    it("es case-insensitive", () => {
      expect(isColdStartError(new Error("NETWORK ERROR"))).toBe(true);
      expect(isColdStartError(new Error("TimeOut exceeded"))).toBe(true);
    });

    it("reconoce un string plano o un objeto con .message, no solo instancias de Error", () => {
      expect(isColdStartError("Network timeout")).toBe(true);
      expect(isColdStartError({ message: "network error" })).toBe(true);
    });

    it("no detecta cold start en un error de validación no relacionado", () => {
      expect(isColdStartError(new Error("El campo es requerido"))).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // Por forma (axios/fetch sin respuesta)
  // -------------------------------------------------------------------------
  describe("por forma del error (sin objeto response)", () => {
    it("detecta un error axios-like con request pero sin response", () => {
      expect(
        isColdStartError({ isAxiosError: true, request: {}, response: undefined }),
      ).toBe(true);
    });

    it("no marca cold start cuando el error axios-like sí tiene response (p. ej. 404)", () => {
      expect(
        isColdStartError({
          isAxiosError: true,
          request: {},
          response: { status: 404, data: {} },
        }),
      ).toBe(false);
    });

    it("no marca cold start una cancelación explícita aunque no tenga response", () => {
      expect(
        isColdStartError({ isAxiosError: true, code: "ERR_CANCELED", request: {} }),
      ).toBe(false);
      expect(isColdStartError({ name: "CanceledError", request: {} })).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // Valores no relacionados
  // -------------------------------------------------------------------------
  describe("valores no relacionados", () => {
    it.each([null, undefined, 42, {}, "Ocurrió un problema inesperado"])(
      "devuelve false para %j",
      (value) => {
        expect(isColdStartError(value)).toBe(false);
      },
    );
  });
});
