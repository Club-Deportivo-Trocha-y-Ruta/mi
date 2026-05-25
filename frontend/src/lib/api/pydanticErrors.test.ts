import { describe, expect, it, vi } from "vitest";
import { AxiosError, AxiosHeaders } from "axios";

import { applyPydanticErrors } from "@/lib/api/pydanticErrors";

interface DummyForm extends Record<string, unknown> {
  first_name: string;
  email: string;
  audiences?: { audience_type?: string }[];
}

function makeAxios422(detail: unknown): AxiosError {
  const err = new AxiosError(
    "Request failed with status code 422",
    "ERR_BAD_REQUEST",
  );
  err.response = {
    status: 422,
    statusText: "Unprocessable Entity",
    data: { detail },
    headers: {},
    config: { headers: new AxiosHeaders() },
  };
  return err;
}

describe("applyPydanticErrors", () => {
  it("mapea cada item del detail array a setError", () => {
    const setError = vi.fn();
    const err = makeAxios422([
      { loc: ["body", "first_name"], msg: "Field required", type: "missing" },
      { loc: ["body", "email"], msg: "Invalid email", type: "value_error" },
    ]);

    const result = applyPydanticErrors<DummyForm>(err, setError);

    expect(result).toBe(true);
    expect(setError).toHaveBeenCalledTimes(2);
    expect(setError).toHaveBeenNthCalledWith(1, "first_name", {
      type: "server",
      message: "Field required",
    });
    expect(setError).toHaveBeenNthCalledWith(2, "email", {
      type: "server",
      message: "Invalid email",
    });
  });

  it("retorna false cuando detail es string (no array)", () => {
    const setError = vi.fn();
    const err = makeAxios422("simple string error");

    const result = applyPydanticErrors<DummyForm>(err, setError);

    expect(result).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });

  it("retorna false en 401 (no Pydantic)", () => {
    const setError = vi.fn();
    const err = new AxiosError("Unauthorized", "ERR_BAD_REQUEST");
    err.response = {
      status: 401,
      statusText: "Unauthorized",
      data: { detail: "token expired" },
      headers: {},
      config: { headers: new AxiosHeaders() },
    };

    const result = applyPydanticErrors<DummyForm>(err, setError);
    expect(result).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });

  it("retorna false en error no-axios (network/500 sin detail iterable)", () => {
    const setError = vi.fn();
    const result = applyPydanticErrors<DummyForm>(
      new Error("kaboom"),
      setError,
    );
    expect(result).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });

  it("retorna false en undefined / null (defensa)", () => {
    const setError = vi.fn();
    expect(applyPydanticErrors<DummyForm>(undefined, setError)).toBe(false);
    expect(applyPydanticErrors<DummyForm>(null, setError)).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });

  it("descarta items malformados (sin loc/msg)", () => {
    const setError = vi.fn();
    const err = makeAxios422([
      { loc: ["body", "first_name"], msg: "ok", type: "missing" },
      { weird: "shape" }, // malformado
      { loc: ["body"], msg: "loc-vacío-tras-prefijo", type: "x" },
    ]);
    const result = applyPydanticErrors<DummyForm>(err, setError);
    expect(result).toBe(true);
    expect(setError).toHaveBeenCalledTimes(1);
  });

  it("soporta nested locs con índices (audiences.[0].audience_type)", () => {
    const setError = vi.fn();
    const err = makeAxios422([
      {
        loc: ["body", "audiences", 0, "audience_type"],
        msg: "Required",
        type: "missing",
      },
    ]);
    const result = applyPydanticErrors<DummyForm>(err, setError);
    expect(result).toBe(true);
    expect(setError).toHaveBeenCalledWith("audiences[0].audience_type", {
      type: "server",
      message: "Required",
    });
  });
});
