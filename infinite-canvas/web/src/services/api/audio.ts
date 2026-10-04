import axios from "axios";

import { audioMimeType, normalizeAudioFormatValue, normalizeAudioSpeedValue, normalizeAudioVoiceValue } from "@/lib/audio-generation";
import { redactSensitiveErrorMessage } from "@/lib/error-sanitizer";
import { uploadMediaFile, type UploadedFile } from "@/services/file-storage";
import { buildApiUrl, modelOptionName, resolveModelRequestConfig, type AiConfig } from "@/stores/use-config-store";

export type AudioMediaType = "speech" | "music";
export type HostAudioProxy = { tasksUrl: string; token: string };
export type AudioRequestOptions = { signal?: AbortSignal; hostProxy?: HostAudioProxy };
export type AudioGenerationResult = { blob?: Blob; url?: string; mimeType?: string };
export type AudioGenerationTask = { id: string; provider: "host" | "openai" | "minimax"; model: string; mediaType: AudioMediaType };
export type AudioGenerationTaskState = { status: "pending" } | { status: "completed"; result: AudioGenerationResult } | { status: "failed"; error: string };

function aiApiUrl(config: AiConfig, path: string) {
    return buildApiUrl(config.baseUrl, path);
}

function aiHeaders(config: AiConfig) {
    return {
        Authorization: `Bearer ${config.apiKey}`,
        "Content-Type": "application/json",
    };
}

export async function requestAudioGeneration(config: AiConfig, prompt: string, options?: AudioRequestOptions): Promise<Blob> {
    const result = await requestAudioGenerationResult(config, prompt, "speech", options);
    if (result.blob) return result.blob;
    if (!result.url) throw new Error("音频接口没有返回可播放内容");
    const response = await fetch(result.url, { signal: options?.signal });
    if (!response.ok) throw new Error("音频内容下载失败");
    return response.blob();
}

export async function requestSpeechGeneration(config: AiConfig, prompt: string, options?: AudioRequestOptions): Promise<AudioGenerationResult> {
    return requestAudioGenerationResult(config, prompt, "speech", options);
}

export async function requestMusicGeneration(config: AiConfig, prompt: string, options?: AudioRequestOptions): Promise<AudioGenerationResult> {
    return requestAudioGenerationResult(config, prompt, "music", options);
}

export async function requestAudioGenerationResult(config: AiConfig, prompt: string, mediaType: AudioMediaType = "speech", options?: AudioRequestOptions): Promise<AudioGenerationResult> {
    if (options?.hostProxy) {
        const task = await createAudioGenerationTask(config, prompt, mediaType, options);
        for (let attempt = 0; attempt < 120; attempt += 1) {
            if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
            const state = await pollAudioGenerationTask(config, task, options);
            if (state.status === "completed") return state.result;
            if (state.status === "failed") throw new Error(state.error);
            await delay(2500, options.signal);
        }
        throw new Error("音频生成超时，请稍后重试");
    }
    const selectedModel = config.model || (mediaType === "speech" ? config.speechModel : config.musicModel) || config.audioModel;
    const requestConfig = resolveModelRequestConfig(config, selectedModel);
    const model = requestConfig.model.trim();
    assertAudioConfig(requestConfig, model, mediaType);

    if (mediaType === "music") return requestMiniMaxMusic(requestConfig, prompt, options);
    const format = normalizeAudioFormatValue(config.audioFormat);
    const instructions = config.audioInstructions.trim();

    try {
        const response = await axios.post<Blob>(
            aiApiUrl(requestConfig, "/audio/speech"),
            {
                model,
                input: prompt,
                voice: normalizeAudioVoiceValue(config.audioVoice),
                response_format: format,
                speed: Number(normalizeAudioSpeedValue(config.audioSpeed)),
                ...(instructions ? { instructions } : {}),
            },
            { headers: aiHeaders(requestConfig), responseType: "blob", signal: options?.signal },
        );
        await assertAudioBlob(response.data);
        return { blob: response.data.type.startsWith("audio/") ? response.data : new Blob([response.data], { type: audioMimeType(format) }) };
    } catch (error) {
        throw new Error(readAxiosError(error, "音频生成失败"));
    }
}

export async function storeGeneratedAudio(result: Blob | AudioGenerationResult, format = "mp3"): Promise<UploadedFile> {
    if (!(result instanceof Blob) && result.url) return { url: result.url, storageKey: "", bytes: 0, mimeType: result.mimeType || audioMimeType(format) };
    const blob = result instanceof Blob ? result : result.blob;
    if (!blob) throw new Error("音频接口没有返回可播放内容");
    const audio = blob.type.startsWith("audio/") ? blob : new Blob([blob], { type: audioMimeType(format) });
    return uploadMediaFile(audio, "audio");
}

function assertAudioConfig(config: AiConfig, model: string, mediaType: AudioMediaType) {
    if (!model) throw new Error("请先配置音频模型");
    if (!config.baseUrl.trim()) throw new Error("请先配置 Base URL");
    if (!config.apiKey.trim()) throw new Error("请先配置 API Key");
    if (mediaType === "music" && config.apiFormat !== "minimax") throw new Error("音乐生成目前需要 MiniMax 渠道");
    if (mediaType === "speech" && config.apiFormat === "gemini") throw new Error("Gemini 调用格式暂不支持语音生成，请使用 OpenAI 或 MiniMax 渠道");
}

export async function createAudioGenerationTask(config: AiConfig, prompt: string, mediaType: AudioMediaType, options?: AudioRequestOptions): Promise<AudioGenerationTask> {
    const selectedModel = config.model || (mediaType === "speech" ? config.speechModel : config.musicModel) || config.audioModel;
    const model = modelOptionName(selectedModel);
    if (options?.hostProxy) {
        const response = await fetch(options.hostProxy.tasksUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Canvas-Session": options.hostProxy.token },
            body: JSON.stringify({
                media_type: mediaType,
                ...(mediaType === "speech" ? { text: prompt } : { prompt }),
                model,
                metadata: {
                    ...(mediaType === "speech" ? { voice_id: config.audioVoice, speed: config.audioSpeed, audio_format: config.audioFormat } : { audio_format: config.audioFormat }),
                },
            }),
            signal: options.signal,
        });
        const data = (await response.json()) as { ok?: boolean; error?: string; task?: { id?: number | string; model?: string } };
        if (!response.ok || !data.ok || !data.task?.id) throw new Error(data.error || "主站音频任务创建失败");
        return { id: String(data.task.id), provider: "host", model: modelOptionName(data.task.model || model), mediaType };
    }
    const requestConfig = resolveModelRequestConfig(config, selectedModel);
    assertAudioConfig(requestConfig, requestConfig.model, mediaType);
    return { id: "direct", provider: requestConfig.apiFormat === "minimax" ? "minimax" : "openai", model: requestConfig.model, mediaType };
}

export async function pollAudioGenerationTask(config: AiConfig, task: AudioGenerationTask, options?: AudioRequestOptions): Promise<AudioGenerationTaskState> {
    if (task.provider !== "host") return { status: "failed", error: "独立音频接口不支持异步任务轮询" };
    if (!options?.hostProxy) throw new Error("主站音频会话已失效，请重新打开画布");
    try {
        const base = options.hostProxy.tasksUrl.replace(/\/+$/, "");
        const response = await fetch(`${base}/${encodeURIComponent(task.id)}`, { headers: { "X-Canvas-Session": options.hostProxy.token }, signal: options.signal, cache: "no-store" });
        const data = (await response.json()) as { ok?: boolean; error?: string; task?: { status?: string; error_message?: string } };
        if (!response.ok || !data.ok || !data.task) throw new Error(data.error || "主站音频任务查询失败");
        const status = String(data.task.status || "").toLowerCase();
        if (["failed", "error", "cancelled", "canceled", "expired"].includes(status)) return { status: "failed", error: data.task.error_message || "音频生成失败" };
        if (!["succeeded", "completed", "success"].includes(status)) return { status: "pending" };
        const contentResponse = await fetch(`${base}/${encodeURIComponent(task.id)}/content`, { headers: { "X-Canvas-Session": options.hostProxy.token }, signal: options.signal, cache: "no-store" });
        const content = (await contentResponse.json()) as { ok?: boolean; url?: string; error?: string };
        if (!contentResponse.ok || !content.ok || !content.url) throw new Error(content.error || "主站音频任务没有返回内容");
        return { status: "completed", result: { url: new URL(content.url, options.hostProxy.tasksUrl).toString(), mimeType: task.mediaType === "music" ? "audio/mpeg" : audioMimeType(config.audioFormat) } };
    } catch (error) {
        if (options.signal?.aborted) throw error;
        return { status: "failed", error: redactSensitiveErrorMessage(error instanceof Error ? error.message : "主站音频任务查询失败", "主站音频任务查询失败") };
    }
}

async function requestMiniMaxMusic(config: AiConfig, prompt: string, options?: AudioRequestOptions): Promise<AudioGenerationResult> {
    const response = await fetch(aiApiUrl(config, "/music_generation"), {
        method: "POST",
        headers: aiHeaders(config),
        body: JSON.stringify({ model: config.model || config.musicModel, prompt }),
        signal: options?.signal,
    });
    const payload = (await response.json()) as { code?: number; msg?: string; data?: { audio?: string; audio_url?: string; audio_base64?: string } };
    if (!response.ok || (typeof payload.code === "number" && payload.code !== 0)) throw new Error(payload.msg || "音乐生成失败");
    const audioUrl = payload.data?.audio_url || payload.data?.audio;
    if (audioUrl?.startsWith("http")) return { url: audioUrl, mimeType: "audio/mpeg" };
    if (audioUrl) return { blob: new Blob([Uint8Array.from(atob(audioUrl), (char) => char.charCodeAt(0))], { type: "audio/mpeg" }) };
    if (payload.data?.audio_base64) return { blob: new Blob([Uint8Array.from(atob(payload.data.audio_base64), (char) => char.charCodeAt(0))], { type: "audio/mpeg" }) };
    throw new Error("音乐接口没有返回音频");
}

function delay(ms: number, signal?: AbortSignal) {
    return new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, ms);
        signal?.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
    });
}

async function assertAudioBlob(blob: Blob) {
    if (!blob.type.includes("json")) return;
    let payload: { code?: number; msg?: string; error?: { message?: string } };
    try {
        payload = JSON.parse(await blob.text()) as { code?: number; msg?: string; error?: { message?: string } };
    } catch {
        return;
    }
    if (typeof payload.code === "number" && payload.code !== 0) throw new Error(payload.msg || "音频生成失败");
    if (payload.error?.message) throw new Error(payload.error.message);
}

function readAxiosError(error: unknown, fallback: string) {
    if (axios.isCancel(error)) return redactSensitiveErrorMessage("请求已取消", fallback);
    if (axios.isAxiosError<{ error?: { message?: string }; msg?: string; code?: number }>(error)) {
        const responseData = error.response?.data;
        return redactSensitiveErrorMessage(responseData?.msg || responseData?.error?.message || statusMessage(error.response?.status, fallback), fallback);
    }
    return redactSensitiveErrorMessage(error instanceof Error ? error.message : fallback, fallback);
}

function statusMessage(status: number | undefined, fallback: string) {
    if (status === 401 || status === 403) return "鉴权失败，请检查 API Key、套餐权限或模型权限";
    if (status === 429) return "请求被限流或额度不足，请稍后重试";
    return status ? `${fallback}（${status}）` : fallback;
}
