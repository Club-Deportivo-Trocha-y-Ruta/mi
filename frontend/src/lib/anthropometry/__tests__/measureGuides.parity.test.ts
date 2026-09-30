import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  MEASURE_GUIDES,
  MEASURE_KEYS,
  PRECHECK_CONDITIONS,
} from "../measureGuides";

// vitest corre con cwd = frontend/; el repo root es su padre.
const JSON_PATH = resolve(process.cwd(), "..", "backend/app/data/anthropometry_measures.json");

interface BackendMeasure {
  key: string;
  label: string;
  donde: string;
  como: string;
  alt: string;
}

const backend = JSON.parse(readFileSync(JSON_PATH, "utf-8")) as {
  precheck: string[];
  measures: BackendMeasure[];
};

describe("measureGuides — paridad con el JSON del backend", () => {
  it("las claves y su orden coinciden", () => {
    expect([...MEASURE_KEYS]).toEqual(backend.measures.map((m) => m.key));
  });

  it("los textos de cada medida son idénticos", () => {
    const fromBackend = Object.fromEntries(
      backend.measures.map(({ key, ...rest }) => [key, rest]),
    );
    expect(MEASURE_GUIDES).toEqual(fromBackend);
  });

  it("las condiciones previas son idénticas", () => {
    expect([...PRECHECK_CONDITIONS]).toEqual(backend.precheck);
  });
});
