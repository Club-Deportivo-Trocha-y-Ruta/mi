/**
 * changeNotice — texto del aviso de cambios y estado del descarte por coach
 * (feature 045, T063).
 */
import { beforeEach, describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import {
  CHANGE_NOTICE_TEXT,
  changeNoticeDismissKey,
  useChangeNoticeOffer,
} from "@/components/newsletter/studio/changeNotice";
import { countWords } from "@/components/newsletter/studio/blockSerializers";

beforeEach(() => {
  window.localStorage.clear();
});

describe("CHANGE_NOTICE_TEXT", () => {
  // El backend rechaza (422) una `coach_note` de más de 60 palabras o 600
  // caracteres y `StageLog` la trunca al leer: el aviso debe poder guardarse
  // tal cual, y con margen para que el coach agregue algo.
  it("cabe en el límite de la nota del entrenador: ≤60 palabras y ≤600 caracteres", () => {
    expect(countWords(CHANGE_NOTICE_TEXT)).toBeLessThanOrEqual(60);
    expect(CHANGE_NOTICE_TEXT.length).toBeLessThanOrEqual(600);
  });

  it("conserva los cuatro puntos del aviso: mediana, percentil por tiempos, resultados sin cambios y la pestaña «Carreras»", () => {
    expect(CHANGE_NOTICE_TEXT).toMatch(/brecha con la mediana/);
    expect(CHANGE_NOTICE_TEXT).toMatch(/percentil se calcula con los tiempos/i);
    expect(CHANGE_NOTICE_TEXT).toMatch(/resultados no cambiaron/i);
    expect(CHANGE_NOTICE_TEXT).toContain("«Carreras»");
  });

  it("no lleva jerga retirada del glosario ni códigos de podio", () => {
    expect(CHANGE_NOTICE_TEXT).not.toMatch(/P1|P3|podio|pelotón|gap/i);
  });
});

describe("changeNoticeDismissKey", () => {
  it("usa la clave versionada por coach", () => {
    expect(changeNoticeDismissKey(7)).toBe("tyr:045-notice-dismissed:v1:7");
    expect(changeNoticeDismissKey("abc")).toBe("tyr:045-notice-dismissed:v1:abc");
  });
});

describe("useChangeNoticeOffer", () => {
  it("por defecto se puede ofrecer y no está descartado", () => {
    const { result } = renderHook(() => useChangeNoticeOffer(7));
    expect(result.current).toMatchObject({ canOffer: true, dismissed: false });
  });

  it("dismiss() lo recuerda en localStorage bajo la clave del coach", () => {
    const { result } = renderHook(() => useChangeNoticeOffer(7));
    act(() => result.current.dismiss());
    expect(result.current.dismissed).toBe(true);
    expect(window.localStorage.getItem("tyr:045-notice-dismissed:v1:7")).toBe("1");
  });

  it("un descarte previo persiste entre montajes (mismo coach)", () => {
    window.localStorage.setItem("tyr:045-notice-dismissed:v1:7", "1");
    const { result } = renderHook(() => useChangeNoticeOffer(7));
    expect(result.current.dismissed).toBe(true);
  });

  it("el descarte de un coach no afecta a otro del mismo navegador", () => {
    window.localStorage.setItem("tyr:045-notice-dismissed:v1:7", "1");
    const { result } = renderHook(() => useChangeNoticeOffer(8));
    expect(result.current.dismissed).toBe(false);
  });

  it("sin usuario no se ofrece y dismiss() no escribe ninguna clave", () => {
    const { result } = renderHook(() => useChangeNoticeOffer(undefined));
    expect(result.current.canOffer).toBe(false);
    act(() => result.current.dismiss());
    expect(window.localStorage.length).toBe(0);
  });
});
