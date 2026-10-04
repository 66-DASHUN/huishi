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

type HostGenerateResponse = {
    ok: boolean;
    images?: Array<{ dataUrl: string }>;
    error?: string;
    balance?: number;
    cost?: number;
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

    const response = await fetch(proxy.generateUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Canvas-Session": proxy.token },
        body: JSON.stringify(body),
        signal: opts.signal,
    });

    const data = (await response.json()) as HostGenerateResponse;

    if (!data.ok || !data.images?.length) {
        throw new Error(data.error || "主站生图代理失败，请稍后重试");
    }

    return data.images.filter((img) => Boolean(img.dataUrl)).map((img) => ({ id: nanoid(), dataUrl: img.dataUrl }));
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
