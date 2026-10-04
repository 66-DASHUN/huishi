import { expect, test } from "bun:test";

test("canvas workspace shell exposes the complete responsive slot contract", async () => {
    const source = await Bun.file(new URL("./canvas-workspace-shell.tsx", import.meta.url)).text();

    for (const attribute of ["data-canvas-workspace-shell", "data-canvas-project-bar", "data-canvas-side-rail", "data-canvas-viewport", "data-canvas-bottom-controls", "data-canvas-assistant-drawer"]) {
        expect(source).toContain(attribute);
    }
    for (const prop of ["projectBar", "sideRail", "canvas", "bottomControls", "assistant", "assistantOpen", "assistantWidth", "mobileToolbar"]) {
        expect(source).toContain(prop);
    }
});

test("desktop rails and assistant are hidden on mobile while the mobile slot is explicit", async () => {
    const source = await Bun.file(new URL("./canvas-workspace-shell.tsx", import.meta.url)).text();

    expect(source).toContain("hidden shrink-0 md:flex");
    expect(source).toContain("hidden min-w-0 max-w-full flex-col");
    expect(source).toContain("md:flex");
    expect(source).toContain("md:hidden");
});

test("closed assistant drawers release pointer input and width", async () => {
    const source = await Bun.file(new URL("./canvas-workspace-shell.tsx", import.meta.url)).text();

    expect(source).toContain("width: assistantOpen ? `${safeAssistantWidth}px` : undefined");
    expect(source).toContain('pointerEvents: assistantOpen ? "auto" : "none"');
    expect(source).toContain("inert={!assistantOpen}");
    expect(source).toContain("{assistantOpen ? assistant : null}");
    expect(source).toContain('assistantOpen ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-2 opacity-0"');
});

test("theme and reduced-motion hooks are present", async () => {
    const source = await Bun.file(new URL("./canvas-workspace-shell.tsx", import.meta.url)).text();

    expect(source).toContain("canvasThemes");
    expect(source).toContain("useThemeStore");
    expect(source).toContain("motion-safe:transition");
    expect(source).toContain("motion-reduce:transition-none");
    expect(source).toContain("data-canvas-motion-surface");
});
