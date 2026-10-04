import { expect, test } from "bun:test";

import { normalizeImageGenerationCount } from "./image-generation-count";

test("negative and zero generation counts fall back to one", () => {
    expect(normalizeImageGenerationCount(-4)).toBe(1);
    expect(normalizeImageGenerationCount(0)).toBe(1);
});

test("generation counts are floored and capped", () => {
    expect(normalizeImageGenerationCount(3.8)).toBe(3);
    expect(normalizeImageGenerationCount(99)).toBe(10);
});
