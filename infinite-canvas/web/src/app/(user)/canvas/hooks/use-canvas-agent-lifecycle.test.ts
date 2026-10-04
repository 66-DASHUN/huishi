import { expect, test } from "bun:test";

import { INITIAL_AGENT_LIFECYCLE, reduceAgentLifecycle } from "./use-canvas-agent-lifecycle";

test("agent close stays mounted through animation and preserves its mode", () => {
    const open = reduceAgentLifecycle(INITIAL_AGENT_LIFECYCLE, { type: "open", mode: "local" });
    const closing = reduceAgentLifecycle(open, { type: "close" });
    const closed = reduceAgentLifecycle(closing, { type: "animation-complete" });

    expect(closing).toEqual({ mounted: true, collapsed: true, closing: true, mode: "local" });
    expect(closed).toEqual({ ...INITIAL_AGENT_LIFECYCLE, mode: "local" });
});

test("reopening during close cancels the pending unmount state", () => {
    const closing = reduceAgentLifecycle({ mounted: true, collapsed: false, closing: false, mode: "online" }, { type: "close" });

    expect(reduceAgentLifecycle(closing, { type: "open" })).toEqual({ mounted: true, collapsed: false, closing: false, mode: "online" });
});

test("hook owns timer cleanup", async () => {
    const source = await Bun.file(new URL("./use-canvas-agent-lifecycle.ts", import.meta.url)).text();

    expect(source).toContain("const clearCloseTimer = useCallback");
    expect(source).toContain("return clearCloseTimer");
    expect(source).toContain("clearCloseTimer();");
});
