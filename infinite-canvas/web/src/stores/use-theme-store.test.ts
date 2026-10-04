import { describe, expect, test } from "bun:test";

import { resolveTheme } from "./use-theme-store";

describe("resolveTheme", () => {
    test("keeps explicit themes", () => {
        expect(resolveTheme("light", true)).toBe("light");
        expect(resolveTheme("dark", false)).toBe("dark");
    });

    test("resolves system from media state", () => {
        expect(resolveTheme("system", true)).toBe("dark");
        expect(resolveTheme("system", false)).toBe("light");
    });
});
