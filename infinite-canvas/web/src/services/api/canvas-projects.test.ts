import { afterEach, describe, expect, test } from "bun:test";

import { buildCanvasProjectPayload, saveCanvasProject } from "./canvas-projects";
import { CanvasNodeType } from "@/app/(user)/canvas/types";
import type { CanvasProject } from "@/app/(user)/canvas/stores/use-canvas-store";

const project: CanvasProject = {
    id: "project-1",
    title: "Test canvas",
    createdAt: "2026-07-15T00:00:00.000Z",
    updatedAt: "2026-07-15T00:01:00.000Z",
    nodes: [{ id: "node-1", type: CanvasNodeType.Text, title: "Text", position: { x: 0, y: 0 }, width: 320, height: 180, metadata: { prompt: "hello" } }],
    connections: [],
    chatSessions: [],
    activeChatId: null,
    backgroundMode: "lines",
    showImageInfo: false,
    viewport: { x: 0, y: 0, k: 1 },
    remoteRev: 3,
    syncStatus: "saved",
};

afterEach(() => {
    Reflect.deleteProperty(globalThis, "fetch");
});

describe("canvas project api", () => {
    test("serializes canvas state into a revision guarded project payload", () => {
        expect(buildCanvasProjectPayload(project, 3)).toEqual({
            project: {
                id: "project-1",
                title: "Test canvas",
                schemaVersion: 1,
                baseRev: 3,
                createdAt: "2026-07-15T00:00:00.000Z",
                updatedAt: "2026-07-15T00:01:00.000Z",
                payload: {
                    nodes: project.nodes,
                    connections: [],
                    chatSessions: [],
                    activeChatId: null,
                    backgroundMode: "lines",
                    showImageInfo: false,
                    viewport: { x: 0, y: 0, k: 1 },
                },
            },
        });
    });

    test("saves existing projects with PATCH and the host session header", async () => {
        globalThis.fetch = (async (url, init) => {
            expect(url).toBe("https://huishi.example/api/canvas/projects/project-1");
            expect(init?.method).toBe("PATCH");
            expect((init?.headers as Record<string, string>)["X-Canvas-Session"]).toBe("token");
            expect(JSON.parse(String(init?.body)).project.baseRev).toBe(3);
            return new Response(JSON.stringify({ ok: true, project: { id: "project-1", rev: 4 } }), { status: 200, headers: { "Content-Type": "application/json" } });
        }) as typeof fetch;

        const saved = await saveCanvasProject("https://huishi.example/api/canvas/projects", "token", project);
        expect(saved.rev).toBe(4);
    });
});
