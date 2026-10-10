import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import { requestHostEstimate, requestHostGeneration } from "./host-image";

const originalFetch = globalThis.fetch;
const originalSetTimeout = globalThis.setTimeout;

// 生产的轮询间隔是 2500ms，测试里没必要真等——把定时器换成"立刻触发"，
// 否则一个用例要跑 5s 以上并撞上 bun 的 5000ms 默认超时。
beforeEach(() => {
    globalThis.setTimeout = ((handler: TimerHandler) => {
        if (typeof handler === "function") handler();
        return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as unknown as typeof setTimeout;
});

afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalSetTimeout;
});

/**
 * 装一个「先提交、再轮询」的假 fetch。
 *
 * 主站已改为异步任务（2026-10-10）：POST 只返回任务号，结果靠轮询拿。
 * 所以断言请求体时要抓**第一次**（提交）请求，而不是最后一次。
 */
function stubSubmitThenPoll(options?: { submitResponse?: unknown; statusResponses?: unknown[] }) {
    const seen: Array<{ url: string; body?: Record<string, unknown> }> = [];
    const statusResponses = options?.statusResponses ?? [
        { ok: true, task: { status: "running" } },
        { ok: true, task: { status: "succeeded" }, images: [{ dataUrl: "data:image/png;base64,AA==" }] },
    ];
    let pollIndex = 0;

    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const isSubmit = init?.method === "POST";
        seen.push({
            url,
            body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined,
        });
        if (isSubmit) {
            return new Response(
                JSON.stringify(options?.submitResponse ?? { ok: true, task: { id: 42 }, cost: 3 }),
                { status: 202 },
            );
        }
        const payload = statusResponses[Math.min(pollIndex, statusResponses.length - 1)];
        pollIndex += 1;
        return new Response(JSON.stringify(payload), { status: 200 });
    }) as typeof fetch;

    return seen;
}

describe("host image model forwarding", () => {
    test("generation payload includes the selected real model", async () => {
        const seen = stubSubmitThenPoll();

        await requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], {
            model: "grok-imagine-image-2.0",
            quality: "auto",
            size: "2048x2048",
            count: 1,
        });

        const submit = seen.find((call) => call.body);
        expect(submit?.body?.model).toBe("grok-imagine-image-2.0");
    });

    test("generation payload strips the local channel namespace", async () => {
        const seen = stubSubmitThenPoll();

        await requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], {
            model: "default::grok-imagine-image-2.0",
            quality: "auto",
            size: "2048x2048",
            count: 1,
        });

        const submit = seen.find((call) => call.body);
        expect(submit?.body?.model).toBe("grok-imagine-image-2.0");
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

describe("host image async polling", () => {
    test("submit returns a task id and the result is fetched by polling", async () => {
        const seen = stubSubmitThenPoll();

        const images = await requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], {
            count: 1,
        });

        expect(images).toHaveLength(1);
        expect(images[0].dataUrl).toBe("data:image/png;base64,AA==");
        // 提交走 POST，查询走 GET 且打到 /<task_id>
        expect(seen.some((call) => call.url.endsWith("/api/canvas/generate/42"))).toBe(true);
    });

    test("submit failure surfaces the server message without polling", async () => {
        const seen = stubSubmitThenPoll({ submitResponse: { ok: false, error: "积分余额不足" } });

        await expect(
            requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], { count: 1 }),
        ).rejects.toThrow("积分余额不足");
        // 提交就被拒时不应继续轮询
        expect(seen).toHaveLength(1);
    });

    test("a failed task surfaces its error message", async () => {
        stubSubmitThenPoll({
            statusResponses: [{ ok: true, task: { status: "failed", error_message: "上游渠道不可用" } }],
        });

        await expect(
            requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], { count: 1 }),
        ).rejects.toThrow("上游渠道不可用");
    });

    test("succeeded but unreadable images must not look like success", async () => {
        // 任务成功、但结果文件读不出来：不能静默当成成功返回空图，
        // 否则用户看到的是"生成好了"却什么都没有。
        stubSubmitThenPoll({
            statusResponses: [{ ok: true, task: { status: "succeeded" }, images: [], images_unavailable: true }],
        });

        await expect(
            requestHostGeneration({ generateUrl: "https://host.example/api/canvas/generate", token: "token" }, "a cat", [], { count: 1 }),
        ).rejects.toThrow(/读取失败/);
    });
});
