import { afterEach, describe, expect, test } from "bun:test";

import { requestHostEstimate, requestHostGeneration } from "./host-image";

const originalFetch = globalThis.fetch;

afterEach(() => {
    globalThis.fetch = originalFetch;
});

describe("host image model forwarding", () => {
    test("generation payload includes the selected real model", async () => {
        let body: Record<string, unknown> | undefined;
        globalThis.fetch = (async (_input, init) => {
            body = JSON.parse(String(init?.body)) as Record<string, unknown>;
            return new Response(JSON.stringify({ ok: true, images: [{ dataUrl: "data:image/png;base64,AA==" }] }), { status: 200 });
        }) as typeof fetch;

        await requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], {
            model: "grok-imagine-image-2.0",
            quality: "auto",
            size: "2048x2048",
            count: 1,
        });

        expect(body?.model).toBe("grok-imagine-image-2.0");
    });

    test("generation payload strips the local channel namespace", async () => {
        let body: Record<string, unknown> | undefined;
        globalThis.fetch = (async (_input, init) => {
            body = JSON.parse(String(init?.body)) as Record<string, unknown>;
            return new Response(JSON.stringify({ ok: true, images: [{ dataUrl: "data:image/png;base64,AA==" }] }), { status: 200 });
        }) as typeof fetch;

        await requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], {
            model: "default::grok-imagine-image-2.0",
            quality: "auto",
            size: "2048x2048",
            count: 1,
        });

        expect(body?.model).toBe("grok-imagine-image-2.0");
    });

    test("estimate payload includes the selected real model", async () => {
        let body: Record<string, unknown> | undefined;
        globalThis.fetch = (async (_input, init) => {
            body = JSON.parse(String(init?.body)) as Record<string, unknown>;
            return new Response(JSON.stringify({ ok: true, cost: 7, billing_mode: "platform" }), { status: 200 });
        }) as typeof fetch;

        await requestHostEstimate({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, {
            model: "gemini-3.1-flash-image",
            resolution: "4K",
            count: 1,
        });

        expect(body?.model).toBe("gemini-3.1-flash-image");
    });
});
