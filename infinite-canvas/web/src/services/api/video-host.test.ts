import { afterEach, describe, expect, test } from "bun:test";

import { createVideoGenerationTask, pollVideoGenerationTask } from "./video";
import { defaultConfig } from "@/stores/use-config-store";

const originalFetch = globalThis.fetch;

afterEach(() => {
    globalThis.fetch = originalFetch;
});

describe("host video proxy", () => {
    test("creates a server-owned task without sending provider credentials", async () => {
        let request: { url: string; init?: RequestInit } | undefined;
        globalThis.fetch = (async (input, init) => {
            request = { url: String(input), init };
            return new Response(JSON.stringify({ ok: true, task: { id: 42, model: "grok-imagine-video" } }), { status: 200 });
        }) as typeof fetch;

        const task = await createVideoGenerationTask(
            { ...defaultConfig, model: "default::grok-imagine-video", videoModel: "default::grok-imagine-video" },
            "A cinematic shot",
            [],
            [],
            [],
            { hostProxy: { tasksUrl: "https://host.example/api/video/tasks", token: "session-token" } },
        );

        expect(task).toEqual({ id: "42", provider: "host", model: "grok-imagine-video" });
        expect(request?.url).toBe("https://host.example/api/video/tasks");
        expect((request?.init?.headers as Record<string, string>).Authorization).toBeUndefined();
        expect((request?.init?.headers as Record<string, string>)["X-Canvas-Session"]).toBe("session-token");
        expect(JSON.parse(String(request?.init?.body)).model).toBe("grok-imagine-video");
    });

    test("polls the server task and resolves its stored content URL", async () => {
        const urls: string[] = [];
        globalThis.fetch = (async (input) => {
            const url = String(input);
            urls.push(url);
            if (url.endsWith("/content")) return new Response(JSON.stringify({ ok: true, url: "/static/uploads/video.mp4" }), { status: 200 });
            return new Response(JSON.stringify({ ok: true, task: { id: 42, status: "succeeded" } }), { status: 200 });
        }) as typeof fetch;

        const state = await pollVideoGenerationTask(
            defaultConfig,
            { id: "42", provider: "host", model: "grok-imagine-video" },
            { hostProxy: { tasksUrl: "https://host.example/api/video/tasks", token: "session-token" } },
        );

        expect(state).toEqual({ status: "completed", result: { url: "https://host.example/static/uploads/video.mp4", mimeType: "video/mp4" } });
        expect(urls).toEqual(["https://host.example/api/video/tasks/42", "https://host.example/api/video/tasks/42/content"]);
    });
});
