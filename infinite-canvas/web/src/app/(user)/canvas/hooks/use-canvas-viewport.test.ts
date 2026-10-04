import { expect, test } from "bun:test";

import { canvasViewportSnapshot } from "./use-canvas-viewport";

test("canvas viewport switches to compact below md", () => {
    expect(canvasViewportSnapshot(390)).toEqual({ compact: true, agentWidth: 390 });
    expect(canvasViewportSnapshot(767)).toEqual({ compact: true, agentWidth: 767 });
    expect(canvasViewportSnapshot(768)).toEqual({ compact: false, agentWidth: 520 });
    expect(canvasViewportSnapshot(1280)).toEqual({ compact: false, agentWidth: 520 });
});

test("assistant panel exposes compact overlay behavior", async () => {
    const source = await Bun.file(new URL("../components/canvas-assistant-panel.tsx", import.meta.url)).text();
    const clientSource = await Bun.file(new URL("../[id]/canvas-client-page.tsx", import.meta.url)).text();

    expect(source).toContain('compact ? "absolute inset-0');
    expect(source).toContain("compact ? null");
    expect(source).toContain('aria-label="关闭 Agent"');
    expect(clientSource).toContain("useCanvasViewport()");
    expect(clientSource).toContain("compact={canvasViewport.compact}");
});
