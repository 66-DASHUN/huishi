import { expect, test } from "bun:test";

import * as capabilities from "./media-model-capabilities";

const buildSliderModel = (capabilities as unknown as Record<string, (...args: unknown[]) => unknown>).buildVideoDurationSliderModel;
const durationAtPosition = (capabilities as unknown as Record<string, (...args: unknown[]) => unknown>).videoDurationFromSliderPosition;

test("continuous model durations expose every integer second on the slider", () => {
    expect(typeof buildSliderModel).toBe("function");
    if (typeof buildSliderModel !== "function" || typeof durationAtPosition !== "function") return;

    const model = buildSliderModel(Array.from({ length: 15 }, (_, index) => index + 1), 7) as Record<string, unknown>;
    expect(model).toMatchObject({ kind: "continuous", min: 1, max: 15, step: 1, value: 7, disabled: false });
    expect(durationAtPosition(model, 12)).toBe(12);
});

test("discrete model durations snap to only supported values", () => {
    expect(typeof buildSliderModel).toBe("function");
    if (typeof buildSliderModel !== "function" || typeof durationAtPosition !== "function") return;

    const model = buildSliderModel([5, 10, 15], 12) as Record<string, unknown>;
    expect(model).toMatchObject({ kind: "discrete", min: 0, max: 2, step: 1, value: 1, disabled: false });
    expect(durationAtPosition(model, 2)).toBe(15);
});

test("fixed duration models keep their single duration locked", () => {
    expect(typeof buildSliderModel).toBe("function");
    if (typeof buildSliderModel !== "function") return;

    const model = buildSliderModel([30], 12) as Record<string, unknown>;
    expect(model).toMatchObject({ kind: "fixed", min: 0, max: 0, value: 0, disabled: true, durations: [30] });
});
