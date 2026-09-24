/**
 * identityGate — lectura del `409 identity_pending` por carga (feature 045).
 *
 * Cuerpo PLANO `{detail: "identity_pending", pending_for_import, review_path}`.
 * El viejo cuerpo anidado (`detail` como objeto con `code`) ya no existe y NO
 * debe reconocerse.
 */
import { describe, expect, it } from "vitest";

import { getIdentityPendingInfo, identityGateMessage } from "@/lib/identityGate";

function axiosError(status: number, data: unknown) {
  return { response: { status, data } };
}

describe("getIdentityPendingInfo", () => {
  it("lee el cuerpo plano: conteo de ESTA carga y ruta de revisión", () => {
    const info = getIdentityPendingInfo(
      axiosError(409, {
        detail: "identity_pending",
        pending_for_import: 3,
        review_path: "/competitions/imports?seccion=identidades&import=7",
      }),
    );
    expect(info).toEqual({
      pending: 3,
      reviewPath: "/competitions/imports?seccion=identidades&import=7",
    });
  });

  it("no reconoce el viejo cuerpo anidado", () => {
    expect(
      getIdentityPendingInfo(
        axiosError(409, {
          detail: { code: "identity_review_pending", pending: 3 },
        }),
      ),
    ).toBeNull();
  });

  it.each([
    ["otro status", axiosError(500, { detail: "identity_pending" })],
    ["otro detail", axiosError(409, { detail: "nothing_pending" })],
    ["sin response", new Error("Network Error")],
    ["no es un objeto", "boom"],
    ["null", null],
  ])("devuelve null si %s", (_label, err) => {
    expect(getIdentityPendingInfo(err)).toBeNull();
  });

  it.each([
    ["absoluta externa", "https://evil.example/x"],
    ["relativa al protocolo", "//evil.example/x"],
    ["sin barra inicial", "competitions/imports"],
    ["ausente", undefined],
  ])("ignora un review_path %s y usa la sección de identidades", (_l, path) => {
    const info = getIdentityPendingInfo(
      axiosError(409, {
        detail: "identity_pending",
        pending_for_import: 1,
        review_path: path,
      }),
    );
    expect(info?.reviewPath).toBe("/competitions/imports?seccion=identidades");
  });

  it("sin pending_for_import numérico cuenta 0 (no rompe)", () => {
    const info = getIdentityPendingInfo(
      axiosError(409, { detail: "identity_pending" }),
    );
    expect(info?.pending).toBe(0);
  });
});

describe("identityGateMessage", () => {
  it("plural (contracts/ui-copy.md §Identity gate)", () => {
    expect(identityGateMessage(3)).toBe(
      "Hay 3 decisiones de identidad pendientes para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.",
    );
  });

  it("singular", () => {
    expect(identityGateMessage(1)).toBe(
      "Hay 1 decisión de identidad pendiente para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.",
    );
  });
});
