import { describe, expect, test } from "bun:test";

import { DESKTOP_MORE_TOOL_IDS, DESKTOP_PRIMARY_TOOL_IDS, MOBILE_MORE_TOOL_IDS, MOBILE_PRIMARY_TOOL_IDS } from "./canvas-toolbar-tools";

describe("mobile canvas tools", () => {
    test("keeps five primary actions and exposes every secondary action", () => {
        expect(MOBILE_PRIMARY_TOOL_IDS).toEqual(["hand", "text", "image", "upload", "more"]);
        expect(MOBILE_MORE_TOOL_IDS).toEqual(["undo", "redo", "video", "audio", "config", "assets", "appearance", "shortcuts", "reset", "clear"]);
        expect(new Set([...MOBILE_PRIMARY_TOOL_IDS, ...MOBILE_MORE_TOOL_IDS]).size).toBe(15);
    });

    test("desktop keeps frequent tools visible and moves low-frequency tools into more", () => {
        expect(DESKTOP_PRIMARY_TOOL_IDS).toEqual(["hand", "undo", "redo", "text", "image", "video", "config", "upload", "appearance", "more"]);
        expect(DESKTOP_MORE_TOOL_IDS).toEqual(["audio", "assets", "shortcuts", "reset", "clear"]);
        expect(new Set([...DESKTOP_PRIMARY_TOOL_IDS, ...DESKTOP_MORE_TOOL_IDS]).size).toBe(15);
    });

    test("desktop toolbar delegates appearance controls", async () => {
        const source = await Bun.file(new URL("./canvas-toolbar.tsx", import.meta.url)).text();

        expect(source).toContain("<CanvasAppearancePanel");
        expect(source).not.toContain("<Segmented");
    });

    test("mobile toolbar has one fixed five-action dock and a labeled more sheet", async () => {
        const source = await Bun.file(new URL("./canvas-mobile-toolbar.tsx", import.meta.url)).text();

        expect(source).toContain('aria-label="画布常用工具"');
        expect(source).toContain('aria-label="更多工具"');
        expect(source).toContain("aria-expanded={moreOpen}");
        expect(source).toContain("grid-cols-5");
        expect(source).toContain('placement="bottom"');
        expect(source).toContain('label="重置视图"');
        expect(source).toContain("runAndClose(onResetView)");
    });

    test("canvas toolbar switches between desktop rail and mobile surfaces", async () => {
        const source = await Bun.file(new URL("./canvas-toolbar.tsx", import.meta.url)).text();

        expect(source).toContain("data-canvas-side-tools");
        expect(source).toContain('aria-label="画布工具"');
        expect(source).toContain("md:flex-col");
        expect(source).toContain("renderMobileToolbar");
        expect(source).toContain("<CanvasMobileToolbar");
    });
});
