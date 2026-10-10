/**
 * 主站宿主模式生图代理
 * 在嵌入模式下替换直接调用第三方 API，改为通过主站后端统一扣费生图。
 */

import { nanoid } from "nanoid";
import { normalizeImageGenerationCount } from "@/lib/image-generation-count";
import { imageToDataUrl } from "@/services/image-storage";
import type { ReferenceImage } from "@/types/image";

export type HostProxyConfig = {
    generateUrl: string;
    token: string;
};

export type HostImageModel = {
    id: string;
    label: string;
    resolutions: string[];
};

export type HostGeneratedImage = {
    id: string;
    dataUrl: string;
};

function hostModelId(model: string | undefined) {
    const value = (model || "").trim();
    const separator = value.indexOf("::");
    return separator >= 0 ? value.slice(separator + 2) : value;
}

type HostGeneratePayload = {
    token: string;
    prompt: string;
    references: Array<{ dataUrl: string }>;
    ratio: string;
    resolution: string;
    quality: string;
    count: number;
    model?: string;
};

/** 提交响应：返回任务号，不再直接给图。 */
type HostSubmitResponse = {
    ok: boolean;
    task?: { id?: number | string };
    error?: string;
    cost?: number;
    balance?: number;
};

/** 轮询响应：任务状态 + 成功时的图片 data URL。 */
type HostStatusResponse = {
    ok: boolean;
    task?: { status?: string; error_message?: string };
    images?: Array<{ dataUrl: string }>;
    /** 任务成功但结果文件读不出来，前端应提示而非当作成功。 */
    images_unavailable?: boolean;
    balance?: number;
    error?: string;
};

/** 已知 WxH → ratio 映射表 */
const SIZE_TO_RATIO: Record<string, string> = {
    "3840x2160": "16:9",
    "2560x1440": "16:9",
    "1536x864": "16:9",
    "2160x3840": "9:16",
    "1440x2560": "9:16",
    "864x1536": "9:16",
    "2048x2048": "1:1",
    "1024x1024": "1:1",
    "2048x1152": "16:9",
    "1152x2048": "9:16",
    "2160x3120": "2:3",
    "1440x2160": "2:3",
    "1024x1536": "2:3",
    "1536x1024": "3:2",
    "2160x1440": "3:2",
    "2048x1536": "4:3",
    "1365x1024": "4:3",
    "1536x2048": "3:4",
    "1024x1365": "3:4",
};

/** 把画布 size 字段解析为主站比例字符串 */
function resolveHostRatio(size: string): string {
    const s = (size || "").trim();
    if (!s || s === "auto") return "1:1";
    // WxH 格式：从映射表或动态计算
    const wxh = s.match(/^(\d+)x(\d+)$/);
    if (wxh) {
        if (SIZE_TO_RATIO[s]) return SIZE_TO_RATIO[s];
        const w = Number(wxh[1]);
        const h = Number(wxh[2]);
        const ratio = w / h;
        if (Math.abs(ratio - 16 / 9) < 0.05) return "16:9";
        if (Math.abs(ratio - 9 / 16) < 0.05) return "9:16";
        if (Math.abs(ratio - 4 / 3) < 0.05) return "4:3";
        if (Math.abs(ratio - 3 / 4) < 0.05) return "3:4";
        if (Math.abs(ratio - 3 / 2) < 0.05) return "3:2";
        if (Math.abs(ratio - 2 / 3) < 0.05) return "2:3";
        return "1:1";
    }
    // ratio 格式（如 "16:9"）
    if (s.includes(":")) return s;
    return "1:1";
}

/** 把画布 size/quality 解析为主站分辨率档位或具体 WxH */
function resolveHostResolution(quality: string, size?: string): string {
    // WxH 格式直接透传
    if (size && /^\d+x\d+$/.test(size.trim())) return size.trim();
    const q = (quality || "").trim().toLowerCase();
    if (q === "low" || q === "1k") return "1K";
    if (q === "high" || q === "4k") return "4K";
    return "2K";
}

export async function requestHostGeneration(
    proxy: HostProxyConfig,
    prompt: string,
    references: ReferenceImage[],
    opts: {
        model?: string;
        quality?: string;
        size?: string;
        count?: number;
        signal?: AbortSignal;
    },
): Promise<HostGeneratedImage[]> {
    const refDataUrls = await Promise.all(references.map(async (r) => ({ dataUrl: (await imageToDataUrl(r)) || r.dataUrl })));

    const body: HostGeneratePayload = {
        token: proxy.token,
        prompt,
        references: refDataUrls.filter((r) => Boolean(r.dataUrl)),
        ratio: resolveHostRatio(opts.size || "1:1"),
        resolution: resolveHostResolution(opts.quality || "auto", opts.size),
        quality: opts.quality || "auto",
        count: normalizeImageGenerationCount(opts.count),
        model: hostModelId(opts.model),
    };

    // 主站已改为**异步任务**：这里只提交，然后轮询等结果。
    //
    // 为什么改：主站此前是在 Web 线程里同步等上游（实测生图平均 22.9s、
    // 最长 43.8s），而它只有 8 个 Web 单元且每个请求独占一个数据库连接，
    // 并发一上来整个站点一起变慢。改为入队后等上游的活交给后台 worker。
    //
    // 对调用方没有影响：本函数签名与返回值都不变，轮询细节封在这里。
    const response = await fetch(proxy.generateUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Canvas-Session": proxy.token },
        body: JSON.stringify(body),
        signal: opts.signal,
    });

    const submitted = (await response.json()) as HostSubmitResponse;

    // 提交阶段的失败（未授权 / 余额不足 / 限流 / 模型不可用）直接抛出，
    // 这些都有明确文案，不需要轮询。
    if (!submitted.ok || !submitted.task?.id) {
        throw new Error(submitted.error || "主站生图代理失败，请稍后重试");
    }

    const statusUrl = `${proxy.generateUrl.replace(/\/+$/, "")}/${encodeURIComponent(String(submitted.task.id))}`;
    // 生成最长可能到 RQ_JOB_TIMEOUT_SECONDS(1200s) + 上游超时，因此轮询上限给足；
    // 真正的终止条件是任务进入 succeeded / failed，不是这个次数。
    const maxAttempts = 480;
    const pollIntervalMs = 2500;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        if (opts.signal?.aborted) throw new DOMException("Aborted", "AbortError");
        await pollDelay(pollIntervalMs, opts.signal);

        const statusResponse = await fetch(statusUrl, {
            headers: { "X-Canvas-Session": proxy.token },
            signal: opts.signal,
            cache: "no-store",
            credentials: "omit",
        });
        const state = (await statusResponse.json()) as HostStatusResponse;
        if (!state.ok || !state.task) {
            // 查询本身失败（会话过期等）不吞掉，直接抛出让上层提示重新打开画布。
            if (state.error) throw new Error(state.error);
            continue;
        }

        const status = String(state.task.status || "").toLowerCase();
        if (status === "failed") {
            throw new Error(state.task.error_message || "主站生图失败，请重新提交");
        }
        if (status !== "succeeded") continue;

        // 任务成功但图读不出来（文件缺失等）时，主站会带上 images_unavailable。
        // 这种情况**没有扣费争议**（记录已建成），但用户需要知道图拿不到。
        if (state.images_unavailable || !state.images?.length) {
            throw new Error("生成已完成，但结果图片读取失败，请重新生成或联系管理员");
        }
        return state.images.filter((img) => Boolean(img.dataUrl)).map((img) => ({ id: nanoid(), dataUrl: img.dataUrl }));
    }

    throw new Error("生成超时，请稍后重试");
}

/** 轮询等待；可被 AbortSignal 中断（画布取消生成时要能立刻退出）。 */
function pollDelay(ms: number, signal?: AbortSignal) {
    return new Promise<void>((resolve, reject) => {
        if (signal?.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
        }
        const timer = setTimeout(() => {
            signal?.removeEventListener("abort", onAbort);
            resolve();
        }, ms);
        function onAbort() {
            clearTimeout(timer);
            reject(new DOMException("Aborted", "AbortError"));
        }
        signal?.addEventListener("abort", onAbort, { once: true });
    });
}

type HostEstimateResponse = { ok: boolean; cost?: number; billing_mode?: string; error?: string };

/** 向主站请求单次生成的积分估算 */
export async function requestHostEstimate(proxy: HostProxyConfig, opts: { model?: string; resolution?: string; count?: number; signal?: AbortSignal }): Promise<{ cost: number; billingMode: string }> {
    const base = proxy.generateUrl.replace(/\/generate$/, "");
    const url = `${base}/estimate`;
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Canvas-Session": proxy.token },
        body: JSON.stringify({
            token: proxy.token,
            resolution: opts.resolution || "2K",
            count: normalizeImageGenerationCount(opts.count),
            model: hostModelId(opts.model),
        }),
        signal: opts.signal,
        mode: "cors",
        credentials: "omit",
    });
    const data = (await response.json()) as HostEstimateResponse;
    if (!data.ok) throw new Error(data.error || "费用预估失败");
    return { cost: data.cost ?? 0, billingMode: data.billing_mode || "platform" };
}
