import { describe, expect, it } from "vitest";

import { MEASURE_KEYS } from "../measureGuides";
import { getMeasureIllustration } from "../measureIllustrations";

describe("measureIllustrations", () => {
  it("resuelve una ilustración .webp por cada medida", () => {
    for (const key of MEASURE_KEYS) {
      expect(getMeasureIllustration(key)).toMatch(new RegExp(`${key}\\.webp`));
    }
  });
});
