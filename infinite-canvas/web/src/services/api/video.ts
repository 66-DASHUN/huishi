import axios from "axios";

import { dataUrlToFile } from "@/lib/image-utils";
import { redactSensitiveErrorMessage } from "@/lib/error-sanitizer";
import { getMediaBlob, uploadMediaFile, type UploadedFile } from "@/services/file-storage";
import { imageToDataUrl } from "@/services/image-storage";
import { boolConfig, buildSeedancePromptText, isSeedanceVideoConfig, normalizeSeedanceCameraMovement, normalizeSeedanceDuration, normalizeSeedanceRatio, normalizeSeedanceResolution, seedanceImageReferenceError, seedanceVideoReferenceError, SEEDANCE_REFERENCE_LIMITS } from "@/lib/seedance-video";
import { buildApiUrl, modelOptionName, resolveModelRequestConfig, type AiConfig } from "@/stores/use-config-store";
import type { ReferenceImage } from "@/types/image";
import type { ReferenceAudio, ReferenceVideo } from "@/types/media";
import { validateVideoSelection } from "@/lib/media-model-capabilities";

type VideoResponse = { id: string; status?: string; error?: { message?: string } };
type ApiVideoResponse = VideoResponse | { code?: number; data?: VideoResponse | null; msg?: string };
type SeedanceTask = {
    id: string;
    status?: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "expired";
    error?: { code?: string; message?: string } | null;
    content?: { video_url?: string; last_frame_url?: string } | null;
};
type ApiEnvelope<T> = T | { code?: number; data?: T | null; msg?: string };
export type HostVideoProxy = { tasksUrl: string; token: string };
type RequestOptions = { signal?: AbortSignal; hostProxy?: HostVideoProxy; taskStorageKey?: string };

function savedHostTask(options?: RequestOptions): { task?: VideoGenerationTask; payload?: Record<string, unknown> } {
    if (!options?.taskStorageKey || typeof window === "undefined") return {};
    try { return JSON.parse(window.localStorage.getItem(options.taskStorageKey) || "{}"); } catch { return {}; }
}
function saveHostTask(options: RequestOptions | undefined, value: object | null) {
    if (!options?.taskStorageKey || typeof window === "undefined") return;
    if (value) window.localStorage.setItem(options.taskStorageKey, JSON.stringify(value));
    else window.localStorage.removeItem(options.taskStorageKey);
}

export type VideoGenerationResult = { blob?: Blob; url?: string; mimeType?: string };
export type VideoGenerationTask = { id: string; provider: "openai" | "seedance" | "grok" | "minimax" | "host"; model: string };
export type VideoGenerationTaskState = { status: "pending" } | { status: "completed"; result: VideoGenerationResult } | { status: "failed"; error: string };

function aiApiUrl(config: AiConfig, path: string) {
    return buildApiUrl(config.baseUrl, path);
}

function aiHeaders(config: AiConfig, contentType?: string) {
    return {
        Authorization: `Bearer ${config.apiKey}`,
        ...(contentType ? { "Content-Type": contentType } : {}),
    };
}

export async function requestVideoGeneration(config: AiConfig, prompt: string, references: ReferenceImage[] = [], videoReferences: ReferenceVideo[] = [], audioReferences: ReferenceAudio[] = [], options?: RequestOptions): Promise<VideoGenerationResult> {
    const task = (options?.hostProxy && savedHostTask(options).task) || await createVideoGenerationTask(config, prompt, references, videoReferences, audioReferences, options);
    const delayMs = task.provider === "seedance" || task.provider === "minimax" || task.provider === "host" ? 5000 : 2500;
    for (let attempt = 0; attempt < 120; attempt += 1) {
        if (options?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
        const state = await pollVideoGenerationTask(config, task, options);
        if (state.status === "completed") { saveHostTask(options, null); return state.result; }
        if (state.status === "failed") { saveHostTask(options, null); throw new Error(state.error); }
        if (attempt === 119) throw new Error(task.provider === "host" ? `视频任务 ${task.id} 仍在后台处理，请到资产库查看结果，不要重复提交` : "视频等待超时，请核对上游任务状态");
        await delay(delayMs, options?.signal);
    }
    throw new Error("视频生成超时，请稍后重试");
}

export async function createVideoGenerationTask(config: AiConfig, prompt: string, references: ReferenceImage[] = [], videoReferences: ReferenceVideo[] = [], audioReferences: ReferenceAudio[] = [], options?: RequestOptions): Promise<VideoGenerationTask> {
    const selectedModel = (config.model || config.videoModel).trim();
    if (options?.hostProxy) return createHostVideoTask(options.hostProxy, config, selectedModel, prompt, references, videoReferences, audioReferences, options);
    const requestConfig = resolveModelRequestConfig(config, selectedModel);
    assertVideoConfig(requestConfig, requestConfig.model);
    if (isSeedanceVideoConfig(requestConfig)) {
        return createSeedanceTask(requestConfig, selectedModel, prompt, references, videoReferences, audioReferences, options);
    }
    if (requestConfig.apiFormat === "grok") {
        return createGrokVideoTask(requestConfig, selectedModel, prompt, options);
    }
    if (requestConfig.apiFormat === "minimax") {
        return createMiniMaxVideoTask(requestConfig, selectedModel, prompt, options);
    }
    if (videoReferences.length || audioReferences.length) {
        throw new Error("当前视频接口不支持参考视频或参考音频，请切换到 Seedance 2.0 / 火山 Agent Plan 模型，或移除参考素材");
    }
    return createOpenAIVideoTask(requestConfig, selectedModel, prompt, references, options);
}

export async function pollVideoGenerationTask(config: AiConfig, task: VideoGenerationTask, options?: RequestOptions): Promise<VideoGenerationTaskState> {
    if (task.provider === "host") {
        if (!options?.hostProxy) throw new Error("主站视频会话已失效，请重新打开画布");
        return pollHostVideoTask(options.hostProxy, task, options);
    }
    const requestConfig = resolveModelRequestConfig(config, task.model);
    assertVideoConfig(requestConfig, requestConfig.model);
    if (task.provider === "seedance") return pollSeedanceTask(requestConfig, task, options);
    if (task.provider === "grok") return pollGrokVideoTask(requestConfig, task, options);
    if (task.provider === "minimax") return pollMiniMaxVideoTask(requestConfig, task, options);
    return pollOpenAIVideoTask(requestConfig, task, options);
}

type HostVideoTaskResponse = {
    ok?: boolean;
    error?: string;
    task?: {
        id?: number | string;
        model?: string;
        status?: string;
        error_message?: string;
        record?: { image_path?: string } | null;
    };
};

async function createHostVideoTask(proxy: HostVideoProxy, config: AiConfig, model: string, prompt: string, references: ReferenceImage[], videoReferences: ReferenceVideo[], audioReferences: ReferenceAudio[], options?: RequestOptions): Promise<VideoGenerationTask> {
    if (!proxy.tasksUrl || !proxy.token) throw new Error("主站视频会话已失效，请重新打开画布");
    const saved = savedHostTask(options);
    const hostModel = config.hostVideoModels?.find((entry) => entry.id === modelOptionName(model));
    const caps = hostModel?.capabilities;
    const channelSpecific = hostModel?.api_format === "dmc_h3" || hostModel?.api_format === "seedance_media";
    const selection = channelSpecific ? validateVideoSelection(caps || {}, config.videoSeconds, config.vquality, config.size) : null;
    if (channelSpecific && (references.length > (caps?.max_reference_images || 0) || videoReferences.length > (caps?.max_reference_videos || 0) || audioReferences.length > (caps?.max_reference_audios || 0) || references.length + videoReferences.length + audioReferences.length > (caps?.max_references || 30))) throw new Error("参考素材超出当前模型限制，请移除不兼容素材后提交");
    const content = channelSpecific || saved.payload ? undefined : await buildHostVideoContent(prompt, references, videoReferences, audioReferences);
    const ownedReferences: Array<{ id: string; role: string }> = [];
    if (channelSpecific && !saved.payload) {
        const mode = config.videoReferenceMode || "reference";
        const upload = async (url: string, kind: string, role: string) => {
            if (!url) throw new Error("参考素材无法读取，请重新上传");
            const response = await fetch(url); if (!response.ok) throw new Error("无法读取参考素材");
            const body = new FormData(); body.set("file", await response.blob(), `reference.${kind === "image" ? "png" : kind === "video" ? "mp4" : "mp3"}`); body.set("kind", kind);
            const uploaded = await fetch(new URL("/api/media/references", proxy.tasksUrl), { method: "POST", headers: { "X-Canvas-Session": proxy.token }, body, signal: options?.signal });
            const result = await uploaded.json();
            if (!uploaded.ok || !result.ok) throw new Error(result.error || "参考素材上传失败");
            ownedReferences.push({ id: result.asset.id, role });
        };
        for (const [index, image] of references.entries()) {
            const role = hostModel?.api_format !== "dmc_h3" || mode === "reference" ? "reference_image" : mode === "keyframes" ? (index === 0 ? "first_frame" : "last_frame") : mode;
            await upload(await imageToDataUrl(image), "image", role);
        }
        for (const video of videoReferences) await upload(await mediaReferenceDataUrl(video.url, video.storageKey), "video", "reference_video");
        for (const audio of audioReferences) await upload(await mediaReferenceDataUrl(audio.url, audio.storageKey), "audio", "reference_audio");
    }
    const payload = saved.payload || {
        prompt,
        model: modelOptionName(model),
        ratio: config.size === "auto" ? "16:9" : config.size || "16:9",
        resolution: normalizeVideoResolution(config.vquality),
        actual_size: normalizeVideoSize(config.size) || "1280x720",
        quality: config.vquality || "auto",
        duration_seconds: Number(normalizeVideoSeconds(config.videoSeconds)),
        generate_audio: boolConfig(config.videoGenerateAudio, true),
        watermark: boolConfig(config.videoWatermark, false),
        content,
        ...(selection || {}),
        references: channelSpecific ? ownedReferences : undefined,
        camera_movement: config.videoCameraMovement || "auto",
        request_key: crypto.randomUUID(),
    };
    saveHostTask(options, { payload });
    try {
        const response = await fetch(proxy.tasksUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Canvas-Session": proxy.token },
            body: JSON.stringify(payload),
            signal: options?.signal,
        });
        const data = (await response.json()) as HostVideoTaskResponse;
        if (!response.ok || !data.ok || !data.task?.id) {
            if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) saveHostTask(options, null);
            throw new Error(data.error || "主站视频任务创建失败");
        }
        const task: VideoGenerationTask = { id: String(data.task.id), provider: "host", model: modelOptionName(model) };
        saveHostTask(options, { payload, task });
        return task;
    } catch (error) {
        if (options?.signal?.aborted) throw error;
        throw new Error(redactSensitiveErrorMessage(error instanceof Error ? error.message : "主站视频任务创建失败", "主站视频任务创建失败"));
    }
}

async function pollHostVideoTask(proxy: HostVideoProxy, task: VideoGenerationTask, options?: RequestOptions): Promise<VideoGenerationTaskState> {
    try {
        const response = await fetch(`${proxy.tasksUrl.replace(/\/+$/, "")}/${encodeURIComponent(task.id)}`, {
            headers: { "X-Canvas-Session": proxy.token },
            signal: options?.signal,
            cache: "no-store",
        });
        const data = (await response.json()) as HostVideoTaskResponse;
        const remote = data.task;
        if (!response.ok || !data.ok || !remote) throw new Error(data.error || "主站视频任务查询失败");
        const status = String(remote.status || "").toLowerCase();
        if (["succeeded", "completed", "success"].includes(status)) {
            const contentResponse = await fetch(`${proxy.tasksUrl.replace(/\/+$/, "")}/${encodeURIComponent(task.id)}/content`, {
                headers: { "X-Canvas-Session": proxy.token },
                signal: options?.signal,
                cache: "no-store",
            });
            const content = (await contentResponse.json()) as { ok?: boolean; url?: string; error?: string };
            if (!contentResponse.ok || !content.ok || !content.url) throw new Error(content.error || "主站视频任务没有返回内容");
            return { status: "completed", result: { url: new URL(content.url, proxy.tasksUrl).toString(), mimeType: "video/mp4" } };
        }
        if (["failed", "error", "cancelled", "canceled", "expired"].includes(status)) return { status: "failed", error: redactSensitiveErrorMessage(remote.error_message, "主站视频生成失败") };
        return { status: "pending" };
    } catch (error) {
        if (options?.signal?.aborted) throw error;
        throw new Error(redactSensitiveErrorMessage(error instanceof Error ? error.message : "主站视频任务查询失败", "主站视频任务查询失败"));
    }
}

async function buildHostVideoContent(prompt: string, references: ReferenceImage[], videoReferences: ReferenceVideo[], audioReferences: ReferenceAudio[]) {
    const content: Array<Record<string, unknown>> = [];
    if (prompt.trim()) content.push({ type: "text", text: prompt.trim() });
    for (const image of references.slice(0, SEEDANCE_REFERENCE_LIMITS.images)) {
        const dataUrl = await imageToDataUrl(image);
        if (dataUrl) content.push({ type: "image_url", image_url: { url: dataUrl }, role: "reference_image" });
    }
    for (const video of videoReferences.slice(0, SEEDANCE_REFERENCE_LIMITS.videos)) {
        const dataUrl = await mediaReferenceDataUrl(video.url, video.storageKey);
        if (dataUrl) content.push({ type: "video_url", video_url: { url: dataUrl }, role: "reference_video" });
    }
    for (const audio of audioReferences.slice(0, SEEDANCE_REFERENCE_LIMITS.audios)) {
        const dataUrl = await mediaReferenceDataUrl(audio.url, audio.storageKey);
        if (dataUrl) content.push({ type: "audio_url", audio_url: { url: dataUrl }, role: "reference_audio" });
    }
    return content;
}

async function mediaReferenceDataUrl(url: string | undefined, storageKey?: string) {
    let blob: Blob | null = storageKey ? await getMediaBlob(storageKey) : null;
    if (!blob && url?.startsWith("blob:")) blob = await (await fetch(url)).blob();
    if (!blob && url?.startsWith("data:")) return url;
    return blob ? blobToDataUrl(blob) : url && isPublicMediaUrl(url) ? url : "";
}

export async function storeGeneratedVideo(result: VideoGenerationResult): Promise<UploadedFile> {
    if (result.blob) return uploadMediaFile(result.blob, "video");
    if (result.url) return { url: result.url, storageKey: "", bytes: 0, mimeType: result.mimeType || "video/mp4" };
    throw new Error("视频接口没有返回可播放的视频");
}

async function createOpenAIVideoTask(config: AiConfig, model: string, prompt: string, references: ReferenceImage[], options?: RequestOptions): Promise<VideoGenerationTask> {
    const body = new FormData();
    body.append("model", modelOptionName(model));
    body.append("prompt", prompt);
    body.append("seconds", normalizeVideoSeconds(config.videoSeconds));
    if (normalizeVideoSize(config.size)) body.append("size", normalizeVideoSize(config.size)!);
    body.append("resolution_name", normalizeVideoResolution(config.vquality));
    body.append("preset", "normal");
    const files = await Promise.all(references.slice(0, 7).map(async (image) => dataUrlToFile({ ...image, dataUrl: await imageToDataUrl(image) })));
    files.forEach((file) => body.append("input_reference[]", file));
    try {
        const created = unwrapVideoResponse((await axios.post<ApiVideoResponse>(aiApiUrl(config, "/videos"), body, { headers: aiHeaders(config), signal: options?.signal })).data);
        if (!created.id) throw new Error("视频接口没有返回任务 ID");
        return { id: created.id, provider: "openai", model };
    } catch (error) {
        throw new Error(readAxiosError(error, "视频任务创建失败"));
    }
}

async function pollOpenAIVideoTask(config: AiConfig, task: VideoGenerationTask, options?: RequestOptions): Promise<VideoGenerationTaskState> {
    try {
        const video = unwrapVideoResponse((await axios.get<ApiVideoResponse>(aiApiUrl(config, `/videos/${task.id}`), { headers: aiHeaders(config), signal: options?.signal })).data);
        if (video.status === "completed") {
            const content = await axios.get<Blob>(aiApiUrl(config, `/videos/${task.id}/content`), { headers: aiHeaders(config), responseType: "blob", signal: options?.signal });
            await assertVideoBlob(content.data);
            return { status: "completed", result: { blob: content.data } };
        }
        if (video.status === "failed" || video.status === "cancelled") return { status: "failed", error: redactSensitiveErrorMessage(video.error?.message, "视频生成失败") };
        return { status: "pending" };
    } catch (error) {
        throw new Error(readAxiosError(error, "视频任务查询失败"));
    }
}

async function createGrokVideoTask(config: AiConfig, model: string, prompt: string, options?: RequestOptions): Promise<VideoGenerationTask> {
    try {
        const payload = { model: modelOptionName(model), prompt, duration: Number(normalizeVideoSeconds(config.videoSeconds)), aspect_ratio: config.size === "auto" ? undefined : config.size };
        const response = await axios.post<ApiEnvelope<{ id?: string; request_id?: string; task_id?: string }>>(aiApiUrl(config, "/videos/generations"), payload, { headers: aiHeaders(config, "application/json"), signal: options?.signal });
        const created = unwrapEnvelope(response.data, "Grok 视频接口没有返回任务");
        const id = created.id || created.request_id || created.task_id;
        if (!id) throw new Error("Grok 视频接口没有返回任务 ID");
        return { id, provider: "grok", model };
    } catch (error) {
        throw new Error(readAxiosError(error, "Grok 视频任务创建失败"));
    }
}

async function pollGrokVideoTask(config: AiConfig, task: VideoGenerationTask, options?: RequestOptions): Promise<VideoGenerationTaskState> {
    try {
        const response = await axios.get<ApiEnvelope<{ status?: string; video_url?: string; url?: string; error?: { message?: string } }>>(aiApiUrl(config, `/videos/${encodeURIComponent(task.id)}`), { headers: aiHeaders(config), signal: options?.signal });
        const payload = unwrapEnvelope(response.data, "Grok 视频接口没有返回任务");
        const status = String(payload.status || "").toLowerCase();
        if (["completed", "succeeded", "done", "success"].includes(status)) {
            const url = payload.video_url || payload.url;
            if (!url) return { status: "failed", error: "Grok 任务成功但没有返回视频地址" };
            return { status: "completed", result: await videoResultFromUrl(url, options) };
        }
        if (["failed", "error", "cancelled", "canceled", "expired"].includes(status)) return { status: "failed", error: redactSensitiveErrorMessage(payload.error?.message, "Grok 视频生成失败") };
        return { status: "pending" };
    } catch (error) {
        throw new Error(readAxiosError(error, "Grok 视频任务查询失败"));
    }
}

async function createMiniMaxVideoTask(config: AiConfig, model: string, prompt: string, options?: RequestOptions): Promise<VideoGenerationTask> {
    try {
        const response = await axios.post<ApiEnvelope<{ task_id?: string; id?: string }>>(aiApiUrl(config, "/video_generation"), { model: modelOptionName(model), prompt, duration: Number(normalizeVideoSeconds(config.videoSeconds)) }, { headers: aiHeaders(config, "application/json"), signal: options?.signal });
        const created = unwrapEnvelope(response.data, "MiniMax 视频接口没有返回任务");
        const id = created.task_id || created.id;
        if (!id) throw new Error("MiniMax 视频接口没有返回任务 ID");
        return { id, provider: "minimax", model };
    } catch (error) {
        throw new Error(readAxiosError(error, "MiniMax 视频任务创建失败"));
    }
}

async function pollMiniMaxVideoTask(config: AiConfig, task: VideoGenerationTask, options?: RequestOptions): Promise<VideoGenerationTaskState> {
    try {
        const response = await axios.get<ApiEnvelope<{ status?: string; file_id?: string; video_url?: string; url?: string; base_resp?: { status_msg?: string } }>>(aiApiUrl(config, "/query/video_generation"), { params: { task_id: task.id }, headers: aiHeaders(config), signal: options?.signal });
        const payload = unwrapEnvelope(response.data, "MiniMax 视频接口没有返回任务");
        const status = String(payload.status || "").toLowerCase();
        if (["completed", "success", "succeeded"].includes(status)) {
            const url = payload.video_url || payload.url;
            if (url) return { status: "completed", result: await videoResultFromUrl(url, options) };
            if (payload.file_id) {
                const fileResponse = await axios.get<ApiEnvelope<{ url?: string; download_url?: string; file_url?: string; file?: { url?: string; download_url?: string } }>>(aiApiUrl(config, "/files/retrieve"), { params: { file_id: payload.file_id }, headers: aiHeaders(config), signal: options?.signal });
                const file = unwrapEnvelope(fileResponse.data, "MiniMax 文件接口没有返回视频");
                const fileUrl = file.url || file.download_url || file.file_url || file.file?.url || file.file?.download_url;
                if (fileUrl) return { status: "completed", result: await videoResultFromUrl(fileUrl, options) };
            }
            return { status: "failed", error: "MiniMax 任务成功但没有返回视频地址" };
        }
        if (["failed", "error", "cancelled", "canceled", "expired"].includes(status)) return { status: "failed", error: redactSensitiveErrorMessage(payload.base_resp?.status_msg, "MiniMax 视频生成失败") };
        return { status: "pending" };
    } catch (error) {
        throw new Error(readAxiosError(error, "MiniMax 视频任务查询失败"));
    }
}

async function createSeedanceTask(config: AiConfig, model: string, prompt: string, references: ReferenceImage[], videoReferences: ReferenceVideo[], audioReferences: ReferenceAudio[], options?: RequestOptions): Promise<VideoGenerationTask> {
    if (audioReferences.length && !references.length && !videoReferences.length) {
        throw new Error("Seedance 参考音频不能单独使用，请同时添加参考图或参考视频");
    }
    const imageReferenceError = seedanceImageReferenceError(modelOptionName(model), references.length);
    if (imageReferenceError) throw new Error(imageReferenceError);
    assertSeedanceVideoReferences(videoReferences);
    assertSeedanceAudioReferences(audioReferences);
    const content = await buildSeedanceContent(config, prompt, references, videoReferences, audioReferences);
    if (!content.length) throw new Error("请输入视频提示词，或连接参考图片/视频/音频");
    const payload = {
        model: modelOptionName(model),
        content,
        ratio: normalizeSeedanceRatio(config.size),
        resolution: normalizeSeedanceResolution(config.vquality, modelOptionName(model)),
        duration: normalizeSeedanceDuration(config.videoSeconds, modelOptionName(model)),
        camera_movement: normalizeSeedanceCameraMovement(config.videoCameraMovement || "auto"),
        generate_audio: boolConfig(config.videoGenerateAudio, true),
        watermark: boolConfig(config.videoWatermark, false),
    };

    try {
        const created = unwrapSeedanceTask((await axios.post<ApiEnvelope<SeedanceTask>>(seedanceApiUrl(config), payload, { headers: aiHeaders(config, "application/json"), signal: options?.signal })).data);
        if (!created.id) throw new Error("Seedance 接口没有返回任务 ID");
        return { id: created.id, provider: "seedance", model };
    } catch (error) {
        throw new Error(readAxiosError(error, "Seedance 任务创建失败"));
    }
}

async function pollSeedanceTask(config: AiConfig, task: VideoGenerationTask, options?: RequestOptions): Promise<VideoGenerationTaskState> {
    try {
        const state = unwrapSeedanceTask((await axios.get<ApiEnvelope<SeedanceTask>>(seedanceApiUrl(config, task.id), { headers: aiHeaders(config), signal: options?.signal })).data);
        if (state.status === "succeeded") {
            const url = state.content?.video_url;
            if (!url) return { status: "failed", error: "Seedance 任务成功但没有返回视频 URL" };
            return { status: "completed", result: await videoResultFromUrl(url, options) };
        }
        if (state.status === "failed" || state.status === "cancelled" || state.status === "expired") {
            return { status: "failed", error: redactSensitiveErrorMessage(state.error?.message, `Seedance 视频生成${state.status === "expired" ? "超时" : "失败"}`) };
        }
        return { status: "pending" };
    } catch (error) {
        throw new Error(readAxiosError(error, "Seedance 任务查询失败"));
    }
}

function assertSeedanceVideoReferences(videoReferences: ReferenceVideo[]) {
    const error = seedanceVideoReferenceError(videoReferences);
    if (error) throw new Error(error);
    let total = 0;
    for (const video of videoReferences) {
        if (!video.durationMs) continue;
        if (video.durationMs < 2000 || video.durationMs > 15000) throw new Error("Seedance 参考视频单个时长需要在 2-15 秒之间");
        total += video.durationMs;
    }
    if (total > 15000) throw new Error("Seedance 参考视频总时长不能超过 15 秒");
}

function assertSeedanceAudioReferences(audioReferences: ReferenceAudio[]) {
    let total = 0;
    for (const audio of audioReferences) {
        if (!audio.durationMs) continue;
        if (audio.durationMs < 2000 || audio.durationMs > 15000) throw new Error("Seedance 参考音频单个时长需要在 2-15 秒之间");
        total += audio.durationMs;
    }
    if (total > 15000) throw new Error("Seedance 参考音频总时长不能超过 15 秒");
}

function seedanceApiUrl(config: AiConfig, taskId?: string) {
    return buildApiUrl(config.baseUrl, `/contents/generations/tasks${taskId ? `/${encodeURIComponent(taskId)}` : ""}`);
}

async function buildSeedanceContent(config: AiConfig, prompt: string, references: ReferenceImage[], videoReferences: ReferenceVideo[], audioReferences: ReferenceAudio[]) {
    const content: Array<Record<string, unknown>> = [];
    const text = buildSeedancePromptText(prompt, references, videoReferences, audioReferences);
    if (text) content.push({ type: "text", text });
    for (const image of references) {
        content.push({ type: "image_url", image_url: { url: await resolveSeedanceImageUrl(config, image) }, role: "reference_image" });
    }
    for (const video of videoReferences.slice(0, SEEDANCE_REFERENCE_LIMITS.videos)) {
        content.push({ type: "video_url", video_url: { url: await resolveSeedanceVideoUrl(video) }, role: "reference_video" });
    }
    for (const audio of audioReferences.slice(0, SEEDANCE_REFERENCE_LIMITS.audios)) {
        content.push({ type: "audio_url", audio_url: { url: await resolveSeedanceAudioUrl(audio) }, role: "reference_audio" });
    }
    return content;
}

async function resolveSeedanceImageUrl(config: AiConfig, image: ReferenceImage) {
    const directUrl = image.url || image.dataUrl;
    if (isPublicMediaUrl(directUrl) || directUrl.startsWith("asset://")) return directUrl;
    const dataUrl = await imageToDataUrl(image);
    if (!dataUrl) throw new Error("参考图读取失败，请换一张图片或重新上传");
    return dataUrl;
}

async function resolveSeedanceVideoUrl(video: ReferenceVideo) {
    if (isPublicMediaUrl(video.url) || video.url.startsWith("asset://")) return video.url;
    let blob: Blob | null = null;
    if (video.storageKey) blob = await getMediaBlob(video.storageKey);
    if (!blob && video.url?.startsWith("blob:")) blob = await (await fetch(video.url)).blob();
    if (!blob) throw new Error("参考视频必须是公网 URL、素材 ID，或本地已保存的视频");
    return blobToDataUrl(blob);
}

async function resolveSeedanceAudioUrl(audio: ReferenceAudio) {
    if (isPublicMediaUrl(audio.url) || audio.url.startsWith("asset://")) return audio.url;
    let blob: Blob | null = null;
    if (audio.storageKey) blob = await getMediaBlob(audio.storageKey);
    if (!blob && audio.url?.startsWith("blob:")) blob = await (await fetch(audio.url)).blob();
    if (!blob) throw new Error("参考音频必须是公网 URL、素材 ID，或本地已保存的音频");
    return blobToDataUrl(blob);
}

async function videoResultFromUrl(url: string, options?: RequestOptions): Promise<VideoGenerationResult> {
    try {
        const response = await axios.get<Blob>(url, { responseType: "blob", signal: options?.signal });
        await assertVideoBlob(response.data);
        return { blob: response.data };
    } catch (error) {
        if (axios.isCancel(error) || options?.signal?.aborted) throw error;
        return { url, mimeType: "video/mp4" };
    }
}

function assertVideoConfig(config: AiConfig, model: string) {
    if (!model) throw new Error("请先配置视频模型");
    if (!config.baseUrl.trim()) throw new Error("请先配置 Base URL");
    if (!config.apiKey.trim()) throw new Error("请先配置 API Key");
    if (config.apiFormat === "gemini") throw new Error("Gemini 调用格式暂不支持视频生成，请使用 OpenAI 格式渠道");
}

function normalizeVideoSeconds(value: string) {
    const seconds = Math.floor(Number(value) || 6);
    return String(Math.max(1, Math.min(20, seconds)));
}

function normalizeVideoSize(value: string) {
    if (value === "auto") return null;
    const size = value || "1280x720";
    if (/^\d+x\d+$/.test(size)) return size;
    return ["9:16", "2:3", "3:4"].includes(size) ? "720x1280" : "1280x720";
}

function normalizeVideoResolution(value: string) {
    if (value === "low") return "480p";
    if (value === "auto" || value === "high" || value === "medium") return "720p";
    const resolution = value.replace(/p$/i, "") || "720";
    return `${resolution}p`;
}

function unwrapVideoResponse(payload: ApiVideoResponse) {
    return unwrapEnvelope(payload, "接口没有返回视频任务");
}

function unwrapSeedanceTask(payload: ApiEnvelope<SeedanceTask>) {
    return unwrapEnvelope(payload, "Seedance 接口没有返回任务");
}

function unwrapEnvelope<T>(payload: ApiEnvelope<T>, emptyMessage: string): T {
    if (!payload) throw new Error(emptyMessage);
    if (typeof payload === "object" && "code" in payload && typeof payload.code === "number") {
        if (payload.code !== 0) throw new Error(payload.msg || "请求失败");
        if (!payload.data) throw new Error(emptyMessage);
        return payload.data;
    }
    return payload as T;
}

function readAxiosError(error: unknown, fallback: string) {
    if (axios.isCancel(error)) return redactSensitiveErrorMessage("请求已取消", fallback);
    if (axios.isAxiosError<{ error?: { message?: string }; msg?: string; code?: number }>(error)) {
        const responseData = error.response?.data;
        return redactSensitiveErrorMessage(responseData?.msg || responseData?.error?.message || statusMessage(error.response?.status, fallback), fallback);
    }
    if (error instanceof DOMException && error.name === "AbortError") return redactSensitiveErrorMessage("请求已取消", fallback);
    return redactSensitiveErrorMessage(error instanceof Error ? error.message : fallback, fallback);
}

function statusMessage(status: number | undefined, fallback: string) {
    if (status === 401 || status === 403) return "鉴权失败，请检查 API Key、套餐权限或模型权限";
    if (status === 429) return "请求被限流或额度不足，请稍后重试";
    return status ? `${fallback}（${status}）` : fallback;
}

async function assertVideoBlob(blob: Blob) {
    if (!blob.type.includes("json")) return;
    let payload: { code?: number; msg?: string; error?: { message?: string } };
    try {
        payload = JSON.parse(await blob.text()) as { code?: number; msg?: string; error?: { message?: string } };
    } catch {
        return;
    }
    if (typeof payload.code === "number" && payload.code !== 0) throw new Error(payload.msg || "视频下载失败");
    if (payload.error?.message) throw new Error(payload.error.message);
}

function isPublicMediaUrl(value: string) {
    return /^https?:\/\//i.test(value || "");
}

function delay(ms: number, signal?: AbortSignal) {
    return new Promise<void>((resolve, reject) => {
        if (signal?.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
        }
        const timer = setTimeout(resolve, ms);
        signal?.addEventListener(
            "abort",
            () => {
                clearTimeout(timer);
                reject(new DOMException("Aborted", "AbortError"));
            },
            { once: true },
        );
    });
}

function blobToDataUrl(blob: Blob) {
    return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("读取本地素材失败"));
        reader.readAsDataURL(blob);
    });
}
