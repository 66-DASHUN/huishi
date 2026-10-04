import { expect, test } from "bun:test";

import { panelWidth } from "./canvas-panel-layout";

test("panel width preserves mobile gutters", () => {
    expect(panelWidth(390)).toBe(366);
    expect(panelWidth(768)).toBe(500);
});

test("canvas node does not keep an unconditional 500px panel", async () => {
    const source = await Bun.file(new URL("../components/canvas-node.tsx", import.meta.url)).text();

    expect(source).not.toContain('className="absolute left-1/2 top-full z-[70] w-[500px]');
    expect(source).toContain("w-[min(500px,calc(100vw-24px))]");
});
