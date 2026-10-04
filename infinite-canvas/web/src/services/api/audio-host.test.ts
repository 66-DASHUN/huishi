import { afterEach, describe, expect, test } from "bun:test";

import { createAudioGenerationTask, pollAudioGenerationTask } from "./audio";
import { defaultConfig } from "@/stores/use-config-store";

const originalFetch = globalThis.fetch;

afterEach(() => {
    globalThis.fetch = originalFetch;
});

describe("host audio proxy", () => {
    test("creates a speech task with an explicit speech media type", async () => {
        let request: { url: string; init?: RequestInit } | undefined;
        globalThis.fetch = (async (input, init) => {
            request = { url: String(input), init };
            return new Response(JSON.stringify({ ok: true, task: { id: 17, model: "speech-2.8-hd" } }), { status: 200 });
        }) as typeof fetch;

        const task = await createAudioGenerationTask(
            { ...defaultConfig, model: "default::speech-2.8-hd", speechModel: "default::speech-2.8-hd" },
            "欢迎使用",
            "speech",
            { hostProxy: { tasksUrl: "https://host.example/api/audio/tasks", token: "session-token" } },
        );

        expect(task).toEqual({ id: "17", provider: "host", model: "speech-2.8-hd", mediaType: "speech" });
        expect(request?.url).toBe("https://host.example/api/audio/tasks");
        expect((request?.init?.headers as Record<string, string>).Authorization).toBeUndefined();
        expect((request?.init?.headers as Record<string, string>)["X-Canvas-Session"]).toBe("session-token");
        expect(JSON.parse(String(request?.init?.body))).toMatchObject({ media_type: "speech", text: "欢迎使用", model: "speech-2.8-hd" });
    });

    test("polls a music task and resolves its stored content URL", async () => {
        const urls: string[] = [];
        globalThis.fetch = (async (input) => {
            const url = String(input);
            urls.push(url);
            if (url.endsWith("/content")) return new Response(JSON.stringify({ ok: true, url: "/static/uploads/music.mp3" }), { status: 200 });
            return new Response(JSON.stringify({ ok: true, task: { id: 18, status: "succeeded" } }), { status: 200 });
        }) as typeof fetch;

        const state = await pollAudioGenerationTask(
            defaultConfig,
            { id: "18", provider: "host", model: "music-3.0", mediaType: "music" },
            { hostProxy: { tasksUrl: "https://host.example/api/audio/tasks", token: "session-token" } },
        );

        expect(state).toEqual({ status: "completed", result: { url: "https://host.example/static/uploads/music.mp3", mimeType: "audio/mpeg" } });
        expect(urls).toEqual(["https://host.example/api/audio/tasks/18", "https://host.example/api/audio/tasks/18/content"]);
    });
});
