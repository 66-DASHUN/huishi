import { describe, expect, test } from "bun:test";

import { alignHostImageModel, alignHostVideoModel, readHostCanvasBootstrap, type HostCanvasSessionPayload } from "./host-canvas-session";

function withTrustedHostFrame(fn: () => void) {
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
    const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
    const parent = {};
    Object.defineProperty(globalThis, "window", { value: { parent }, configurable: true });
    Object.defineProperty(globalThis, "document", { value: { referrer: "https://huishi.example/workspace" }, configurable: true });
    try {
        fn();
    } finally {
        if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
        else Reflect.deleteProperty(globalThis, "window");
        if (originalDocument) Object.defineProperty(globalThis, "document", originalDocument);
        else Reflect.deleteProperty(globalThis, "document");
    }
}

function hostSearch(overrides: Record<string, string> = {}) {
    return new URLSearchParams({
        host_mode: "huishi",
        host_session_token: "token",
        host_session_verify_url: "https://huishi.example/api/canvas/session/verify",
        host_assets_library_url: "https://huishi.example/api/canvas/assets",
        host_generate_url: "https://huishi.example/api/canvas/generate",
        host_video_tasks_url: "https://huishi.example/api/video/tasks",
        host_chat_url: "https://huishi.example/api/canvas/chat",
        host_projects_url: "https://huishi.example/api/canvas/projects",
        host_origin: "https://huishi.example",
        ...overrides,
    });
}

describe("readHostCanvasBootstrap", () => {
    test("accepts the trusted canvas projects endpoint", () => {
        withTrustedHostFrame(() => {
            expect(readHostCanvasBootstrap(hostSearch())?.projectsUrl).toBe("https://huishi.example/api/canvas/projects");
        });
    });

    test("rejects a projects endpoint from another origin", () => {
        withTrustedHostFrame(() => {
            expect(readHostCanvasBootstrap(hostSearch({ host_projects_url: "https://evil.example/api/canvas/projects" }))).toBeNull();
        });
    });

    test("derives the video task endpoint for older host embeds", () => {
        withTrustedHostFrame(() => {
            const search = hostSearch();
            search.delete("host_video_tasks_url");
            expect(readHostCanvasBootstrap(search)?.videoTasksUrl).toBe("https://huishi.example/api/video/tasks");
        });
    });
});

test("host session payload carries backend image model catalog", () => {
    const payload: HostCanvasSessionPayload = {
        authenticated: true,
        image_models: [{ id: "grok-imagine-image-2.0", label: "grok-imagine 2.0", resolutions: ["1K", "2K"] }],
    };
    expect(payload.image_models?.[0].id).toBe("grok-imagine-image-2.0");
});

test("host session payload carries separate speech and music catalogs", () => {
    const payload: HostCanvasSessionPayload = {
        authenticated: true,
        speech_models: [{ id: "speech-2.8-hd", label: "MiniMax Speech 2.8 HD" }],
        music_models: [{ id: "music-3.0", label: "MiniMax Music 3.0" }],
    };

    expect(payload.speech_models?.[0].id).toBe("speech-2.8-hd");
    expect(payload.music_models?.[0].id).toBe("music-3.0");
});

test("host session aligns a stale local video model to the first enabled backend model", () => {
    const models = [
        { id: "grok-imagine-video", label: "grok-imagine" },
        { id: "seedance-2.0", label: "Seedance 2.0" },
    ];

    expect(alignHostVideoModel("default::sora-2", models)).toBe("grok-imagine-video");
    expect(alignHostVideoModel("default::seedance-2.0", models)).toBe("seedance-2.0");
    expect(alignHostVideoModel("default::sora-2", [])).toBe("");
});

test("host session aligns a stale local image model to the first enabled backend model", () => {
    const models = [
        { id: "grok-imagine-image-2.0", label: "grok-imagine 2.0", resolutions: ["1K", "2K"] },
        { id: "gemini-3.1-flash-image", label: "Nano Banana 2", resolutions: ["1K", "2K", "4K"] },
    ];

    expect(alignHostImageModel("default::gpt-image-2", models)).toBe("grok-imagine-image-2.0");
    expect(alignHostImageModel("grok-imagine-image-2.0", models)).toBe("grok-imagine-image-2.0");
    expect(alignHostImageModel("default::gemini-3.1-flash-image", models)).toBe("gemini-3.1-flash-image");
    expect(alignHostImageModel("default::gpt-image-2", [])).toBe("");
});
