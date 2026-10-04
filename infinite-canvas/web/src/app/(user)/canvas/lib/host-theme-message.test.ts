import { describe, expect, test } from "bun:test";

import { parseHostThemeMessage } from "./host-canvas-session";

describe("parseHostThemeMessage", () => {
    test("accepts a valid host theme", () => {
        expect(parseHostThemeMessage({ type: "huishi-theme-change", preference: "system", resolvedTheme: "dark" })).toEqual({
            type: "huishi-theme-change",
            preference: "system",
            resolvedTheme: "dark",
        });
    });

    test("rejects invalid values", () => {
        expect(parseHostThemeMessage(null)).toBeNull();
        expect(parseHostThemeMessage({ type: "huishi-theme-change", preference: "blue", resolvedTheme: "dark" })).toBeNull();
        expect(parseHostThemeMessage({ type: "huishi-theme-change", preference: "dark", resolvedTheme: "system" })).toBeNull();
    });
});
