"use client";

import { useEffect, useState } from "react";
import { ArrowUp, LoaderCircle, Square } from "lucide-react";
import { Button, ConfigProvider } from "antd";

import { ModelPicker } from "@/components/model-picker";
import { defaultConfig, useConfigStore, useEffectiveConfig, type AiConfig } from "@/stores/use-config-store";
import { CreditSymbol, requestCreditCost } from "@/constant/credits";
import { canvasThemes } from "@/lib/canvas-theme";
import { isSeedanceVideoModel, normalizeSeedanceCameraMovement, normalizeSeedanceDuration, normalizeSeedanceRatio, normalizeSeedanceResolution } from "@/lib/seedance-video";
import { normalizeImageGenerationCount } from "@/lib/image-generation-count";
import { useThemeStore } from "@/stores/use-theme-store";
import { useHostCredits } from "../hooks/use-host-credits";
import { navigateFromCanvas } from "../lib/canvas-navigation-guard";
import { canvasSettingsHref } from "../lib/host-canvas-session";
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";
import { CanvasImageSettingsPopover } from "./canvas-image-settings-popover";
import { CanvasAudioSettingsPopover, type CanvasAudioSettingKey } from "./canvas-audio-settings-popover";
import { CanvasMusicSettingsPopover } from "./canvas-music-settings-popover";
import { CanvasResourceMentionTextarea } from "./canvas-resource-mention-textarea";
import { CanvasVideoSettingsPopover } from "./canvas-video-settings-popover";
import { CanvasNodeType, type CanvasGenerationMode, type CanvasNodeData } from "../types";
import type { CanvasResourceReference } from "../utils/canvas-resource-references";

export type CanvasNodeGenerationMode = CanvasGenerationMode;

type CanvasNodePromptPanelProps = {
    node: CanvasNodeData;
    isRunning: boolean;
    onPromptChange: (nodeId: string, prompt: string) => void;
    onConfigChange: (nodeId: string, patch: Partial<CanvasNodeData["metadata"]>) => void;
    onGenerate: (nodeId: string, mode: CanvasNodeGenerationMode, prompt: string) => void;
    onStop: (nodeId: string) => void;
    mentionReferences?: CanvasResourceReference[];
    onImageSettingsOpenChange?: (open: boolean) => void;
};

export function CanvasNodePromptPanel({ node, isRunning, onPromptChange, onConfigChange, onGenerate, onStop, mentionReferences = [], onImageSettingsOpenChange }: CanvasNodePromptPanelProps) {
    const globalConfig = useEffectiveConfig();
    const theme = canvasThemes[useThemeStore((state) => state.theme)];
    const mode = defaultMode(node);
    const config = buildNodeConfig(globalConfig, node, mode);
    const hasTextContent = node.type === CanvasNodeType.Text && Boolean(node.metadata?.content?.trim());
    const hasImageContent = node.type === CanvasNodeType.Image && Boolean(node.metadata?.content);
    const isEditingExistingContent = hasTextContent || hasImageContent;
    const [prompt, setPrompt] = useState(isEditingExistingContent ? "" : node.metadata?.prompt || "");
    const count = normalizeImageGenerationCount(config.count);
    const localCredits = requestCreditCost({ channelMode: config.channelMode, model: config.model, count: mode === "image" ? count : 1 });
    const resolution = node.metadata?.resolution || "2K";
    const hostCredits = useHostCredits({ model: mode === "image" ? config.model : undefined, resolution, count: mode === "image" ? count : 1 });
    const hostImageModels = useCanvasHostSessionStore((state) => state.imageModels);
    const hostVideoModels = useCanvasHostSessionStore((state) => state.videoModels);
    const hostSpeechModels = useCanvasHostSessionStore((state) => state.speechModels);
    const hostMusicModels = useCanvasHostSessionStore((state) => state.musicModels);
    const credits = hostCredits ?? localCredits;
    const hostOrigin = useCanvasHostSessionStore((state) => state.hostOrigin);
    const isGenerating = useCanvasHostSessionStore((state) => state.isGenerating);
    const requiresHostSession = useCanvasHostSessionStore((state) => state.requiresHostSession);

    const handleMissingConfig = () => {
        const settingsHref = canvasSettingsHref(hostOrigin, requiresHostSession);
        if (settingsHref) navigateFromCanvas(settingsHref, isGenerating);
    };

    useEffect(() => {
        setPrompt(isEditingExistingContent ? "" : node.metadata?.prompt || "");
    }, [isEditingExistingContent, node.id]);

    const updatePrompt = (value: string) => {
        setPrompt(value);
        if (!isEditingExistingContent) onPromptChange(node.id, value);
    };

    const submit = () => {
        const text = prompt.trim();
        if (!text || isRunning) return;
        onGenerate(node.id, mode, text);
        setPrompt("");
    };

    return (
        <ConfigProvider
            theme={{
                token: {
                    colorBgContainer: theme.node.fill,
                    colorBgElevated: theme.toolbar.panel,
                    colorBorder: theme.node.stroke,
                    colorPrimary: theme.node.activeStroke,
                    colorText: theme.node.text,
                    colorTextSecondary: theme.node.muted,
                    colorTextPlaceholder: theme.node.placeholder,
                    colorFillSecondary: theme.toolbar.itemHover,
                    controlItemBgActive: theme.toolbar.activeBg,
                    colorTextLightSolid: theme.node.panel,
                },
                components: {
                    Select: { optionActiveBg: theme.toolbar.itemHover, optionSelectedBg: theme.toolbar.activeBg },
                    Button: { defaultBg: theme.node.fill, defaultBorderColor: theme.node.stroke, defaultColor: theme.node.text },
                },
            }}
        >
            <div
                className="rounded-lg border p-3"
                style={{ background: theme.toolbar.panel, borderColor: theme.toolbar.border, color: theme.node.text }}
                onMouseDown={(event) => event.stopPropagation()}
                onPointerDown={(event) => event.stopPropagation()}
                onWheel={(event) => event.stopPropagation()}
            >
                <CanvasResourceMentionTextarea
                    value={prompt}
                    references={mentionReferences}
                    onChange={updatePrompt}
                    onSubmit={submit}
                    className="thin-scrollbar h-24 w-full resize-none rounded-md border px-3 py-2 text-sm leading-5 outline-none"
                    style={{ background: theme.node.fill, borderColor: theme.node.stroke, color: theme.node.text }}
                    placeholder={promptPlaceholder(mode, hasImageContent, hasTextContent)}
                />

                <div className="mt-2 flex min-w-0 items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                        {mode === "image" ? (
                            <>
                                <ModelPicker
                                    config={config}
                                    value={config.model}
                                    onChange={(model) => onConfigChange(node.id, { model })}
                                    capability="image"
                                    onMissingConfig={handleMissingConfig}
                                    availableModels={requiresHostSession ? hostImageModels : undefined}
                                />
                                <CanvasImageSettingsPopover
                                    config={config}
                                    placement="topLeft"
                                    buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-md !px-3"
                                    onConfigChange={(key, value) => onConfigChange(node.id, key === "count" ? { count: Number(value) || 1 } : { [key]: value })}
                                    onMissingConfig={handleMissingConfig}
                                    onOpenChange={onImageSettingsOpenChange}
                                />
                            </>
                        ) : mode === "video" ? (
                            <>
                                <ModelPicker
                                    config={config}
                                    value={config.model}
                                    onChange={(model) => onConfigChange(node.id, videoModelPatch(config, model))}
                                    capability="video"
                                    onMissingConfig={handleMissingConfig}
                                    availableModels={requiresHostSession ? hostVideoModels : undefined}
                                />
                                <CanvasVideoSettingsPopover config={config} buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-md !px-3" onConfigChange={(key, value) => onConfigChange(node.id, videoConfigPatch(key, value))} />
                            </>
                        ) : mode === "audio" ? (
                            <>
                                <ModelPicker
                                    config={config}
                                    value={config.model}
                                    onChange={(model) => onConfigChange(node.id, { model })}
                                    capability="speech"
                                    onMissingConfig={handleMissingConfig}
                                    availableModels={requiresHostSession ? hostSpeechModels : undefined}
                                />
                                <CanvasAudioSettingsPopover config={config} buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-md !px-3" onConfigChange={(key, value) => onConfigChange(node.id, audioConfigPatch(key, value))} />
                            </>
                        ) : mode === "speech" ? (
                            <>
                                <ModelPicker
                                    config={config}
                                    value={config.model}
                                    onChange={(model) => onConfigChange(node.id, { model })}
                                    capability="speech"
                                    onMissingConfig={handleMissingConfig}
                                    availableModels={requiresHostSession ? hostSpeechModels : undefined}
                                />
                                <CanvasAudioSettingsPopover config={config} buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-md !px-3" onConfigChange={(key, value) => onConfigChange(node.id, audioConfigPatch(key, value))} />
                            </>
                        ) : mode === "music" ? (
                            <>
                                <ModelPicker
                                    config={config}
                                    value={config.model}
                                    onChange={(model) => onConfigChange(node.id, { model })}
                                    capability="music"
                                    onMissingConfig={handleMissingConfig}
                                    availableModels={requiresHostSession ? hostMusicModels : undefined}
                                />
                                <CanvasMusicSettingsPopover config={config} buttonClassName="!h-10 !max-w-[170px] !justify-start !rounded-md !px-3" onConfigChange={(key, value) => onConfigChange(node.id, { [key]: value })} />
                            </>
                        ) : (
                            <ModelPicker config={config} value={config.model} onChange={(model) => onConfigChange(node.id, { model })} capability="text" onMissingConfig={handleMissingConfig} />
                        )}
                    </div>
                    <Button
                        type="primary"
                        className="!h-10 !min-w-16 shrink-0 !rounded-md !px-3"
                        danger={isRunning}
                        disabled={!isRunning && !prompt.trim()}
                        onClick={() => (isRunning ? onStop(node.id) : submit())}
                        aria-label={isRunning ? "停止生成" : "生成"}
                    >
                        <span className="flex items-center gap-1.5">
                            {isRunning ? (
                                <>
                                    <LoaderCircle className="size-4 animate-spin" />
                                    <Square className="size-3.5 fill-current" />
                                    <span className="text-xs font-medium">停止</span>
                                </>
                            ) : (
                                <>
                                    <span className="inline-flex items-center gap-1 text-xs font-medium tabular-nums">
                                        <CreditSymbol />
                                        {credits.toLocaleString()}
                                    </span>
                                    <ArrowUp className="size-4" />
                                </>
                            )}
                        </span>
                    </Button>
                </div>
            </div>
        </ConfigProvider>
    );
}

function defaultMode(node: CanvasNodeData): CanvasNodeGenerationMode {
    if (node.type === CanvasNodeType.Text) return "text";
    if (node.type === CanvasNodeType.Video) return "video";
    if (node.type === CanvasNodeType.Audio) return node.metadata?.audioKind || "speech";
    return "image";
}

function buildNodeConfig(globalConfig: AiConfig, node: CanvasNodeData, mode: CanvasNodeGenerationMode): AiConfig {
    const defaultModel =
        mode === "image"
            ? globalConfig.imageModel
            : mode === "video"
              ? globalConfig.videoModel
              : mode === "music"
                ? globalConfig.musicModel
                : mode === "speech" || mode === "audio"
                  ? globalConfig.speechModel || globalConfig.audioModel
                  : globalConfig.textModel;
    return {
        ...globalConfig,
        model: node.metadata?.model || defaultModel || (mode === "music" ? defaultConfig.musicModel : mode === "speech" || mode === "audio" ? defaultConfig.speechModel : globalConfig.model || defaultConfig.model),
        quality: node.metadata?.quality || globalConfig.quality || defaultConfig.quality,
        size: node.metadata?.size || globalConfig.size || defaultConfig.size,
        videoSeconds: node.metadata?.seconds || globalConfig.videoSeconds || defaultConfig.videoSeconds,
        vquality: node.metadata?.vquality || globalConfig.vquality || defaultConfig.vquality,
        videoCameraMovement: node.metadata?.cameraMovement || globalConfig.videoCameraMovement || defaultConfig.videoCameraMovement,
        videoGenerateAudio: node.metadata?.generateAudio || globalConfig.videoGenerateAudio || defaultConfig.videoGenerateAudio,
        videoWatermark: node.metadata?.watermark || globalConfig.videoWatermark || defaultConfig.videoWatermark,
        audioVoice: node.metadata?.audioVoice || globalConfig.audioVoice || defaultConfig.audioVoice,
        audioFormat: node.metadata?.audioFormat || globalConfig.audioFormat || defaultConfig.audioFormat,
        audioSpeed: node.metadata?.audioSpeed || globalConfig.audioSpeed || defaultConfig.audioSpeed,
        audioInstructions: node.metadata?.audioInstructions || globalConfig.audioInstructions || defaultConfig.audioInstructions,
        musicLyrics: node.metadata?.musicLyrics || globalConfig.musicLyrics || defaultConfig.musicLyrics,
        musicInstrumental: node.metadata?.musicInstrumental || globalConfig.musicInstrumental || defaultConfig.musicInstrumental,
        musicReferenceUrl: node.metadata?.musicReferenceUrl || globalConfig.musicReferenceUrl || defaultConfig.musicReferenceUrl,
        count: String(node.metadata?.count || (mode === "image" ? globalConfig.canvasImageCount || globalConfig.count : globalConfig.count) || defaultConfig.count),
    };
}

function videoModelPatch(config: AiConfig, model: string) {
    if (!isSeedanceVideoModel(model)) return { model };
    return {
        model,
        seconds: String(normalizeSeedanceDuration(config.videoSeconds, model)),
        vquality: normalizeSeedanceResolution(config.vquality, model),
        size: normalizeSeedanceRatio(config.size),
        cameraMovement: normalizeSeedanceCameraMovement(config.videoCameraMovement || "auto"),
    };
}

function promptPlaceholder(mode: CanvasNodeGenerationMode, hasImageContent: boolean, hasTextContent: boolean) {
    if (mode === "video") return "描述要生成的视频内容";
    if (mode === "audio" || mode === "speech") return "输入要合成的语音内容";
    if (mode === "music") return "描述要生成的音乐内容";
    if (mode === "image") return hasImageContent ? "请输入你想要把这张图修改成什么" : "描述要生成的图片内容";
    return hasTextContent ? "请输入你想要将本段文本修改成什么" : "请输入你想要生成的文本内容";
}

function videoConfigPatch(key: keyof AiConfig, value: string) {
    if (key === "videoSeconds") return { seconds: value };
    if (key === "videoCameraMovement") return { cameraMovement: value };
    if (key === "videoGenerateAudio") return { generateAudio: value };
    if (key === "videoWatermark") return { watermark: value };
    return { [key]: value };
}

function audioConfigPatch(key: CanvasAudioSettingKey, value: string) {
    if (key === "audioVoice") return { audioVoice: value };
    if (key === "audioFormat") return { audioFormat: value };
    if (key === "audioSpeed") return { audioSpeed: value };
    return { audioInstructions: value };
}
