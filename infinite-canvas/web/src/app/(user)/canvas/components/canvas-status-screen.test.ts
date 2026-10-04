import { expect, test } from "bun:test";

import { CANVAS_STATUS_COPY } from "./canvas-status-screen";

test("every canvas status has clear copy and a user action", () => {
    for (const status of ["session", "project", "offline", "error"] as const) {
        expect(CANVAS_STATUS_COPY[status].title).toBeTruthy();
        expect(CANVAS_STATUS_COPY[status].description).toBeTruthy();
        expect(CANVAS_STATUS_COPY[status].action).toBeTruthy();
    }
});

test("canvas loading and failure shells use the shared status screen", async () => {
    const statusSource = await Bun.file(new URL("./canvas-status-screen.tsx", import.meta.url)).text();
    const guardSource = await Bun.file(new URL("./canvas-host-session-guard.tsx", import.meta.url)).text();
    const routeSource = await Bun.file(new URL("../[id]/page.tsx", import.meta.url)).text();
    const clientSource = await Bun.file(new URL("../[id]/canvas-client-page.tsx", import.meta.url)).text();

    expect(statusSource).toContain('role={loading ? "status" : "alert"}');
    expect(guardSource).toContain("<CanvasStatusScreen");
    expect(routeSource).toContain("<CanvasStatusScreen");
    expect(clientSource).toContain("navigator.onLine");
    expect(clientSource).toContain('status="offline"');
    expect(clientSource).toContain('status="error"');
});
