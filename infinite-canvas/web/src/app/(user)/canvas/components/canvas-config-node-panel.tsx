"use client";

import { type CSSProperties } from "react";
import { Image as ImageIcon, LoaderCircle, MessageSquare, Mic2, Music2, Play, Settings2, Square, Video } from "lucide-react";
import { Button, ConfigProvider, Segmented } from "antd";

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
import { CanvasVideoSettingsPopover } from "./canvas-video-settings-popover";
import type { CanvasGenerationMode, CanvasNodeData, CanvasNodeMetadata } from "../types";

type CanvasConfigNodePanelProps = {
    node: CanvasNodeData;
    isRunning: boolean;
    inputSummary: { textCount: number; imageCount: number; videoCount: number; audioCount: number };
    onConfigChange: (nodeId: string, patch: Partial<CanvasNodeMetadata>) => void;
    onGenerate: (nodeId: string) => void;
    onStop: (nodeId: string) => void;
    onComposerToggle: () => void;
};

export function CanvasConfigNodePanel({ node, isRunning, inputSummary, onConfigChange, onGenerate, onStop, onComposerToggle }: CanvasConfigNodePanelProps) {
    const globalConfig = useEffectiveConfig();
    const theme = canvasThemes[useThemeStore((state) => state.theme)];
    const mode = node.metadata?.generationMode === "audio" ? "speech" : node.metadata?.generationMode || "image";
    const config = buildNodeConfig(globalConfig, node, mode);
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
    const chipStyle = { background: theme.node.fill, borderColor: theme.node.stroke, color: theme.node.text };
    const hasAnyInput = Boolean(inputSummary.textCount || inputSummary.imageCount || inputSummary.videoCount || inputSummary.audioCount);
    const hasComposerContent = Boolean((node.metadata?.composerContent ?? node.metadata?.prompt ?? "").trim());
    const canGenerate = hasComposerContent || (mode === "speech" ? inputSummary.textCount > 0 : hasAnyInput);
    const handleMissingConfig = () => {
        const settingsHref = canvasSettingsHref(hostOrigin, requiresHostSession);
        if (settingsHref) navigateFromCanvas(settingsHref, isGenerating);
    };
    const handleModeChange = (nextMode: CanvasGenerationMode) => {
        const nextModel =
            nextMode === "image"
                ? globalConfig.imageModel
                : nextMode === "video"
                  ? globalConfig.videoModel
                  : nextMode === "music"
                    ? globalConfig.musicModel
                    : nextMode === "speech" || nextMode === "audio"
                      ? globalConfig.speechModel || globalConfig.audioModel
                      : globalConfig.textModel;
        onConfigChange(node.id, { generationMode: nextMode, model: nextModel });
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
                    Segmented: { itemSelectedBg: theme.toolbar.activeBg, itemSelectedColor: theme.toolbar.activeText, itemHoverBg: theme.toolbar.itemHover, itemColor: theme.toolbar.item, trackBg: theme.node.fill },
                    Select: { optionActiveBg: theme.toolbar.itemHover, optionSelectedBg: theme.toolbar.activeBg },
                    Button: { defaultBg: theme.node.fill, defaultBorderColor: theme.node.stroke, defaultColor: theme.node.text },
                },
            }}
        >
            <div className="flex h-full w-full cursor-move flex-col px-2.5 pb-2.5 pt-5 text-xs" style={{ color: theme.node.text }} onWheel={(event) => event.stopPropagation()}>
                <div className="mb-1.5 flex items-center justify-between gap-2">
                    <div className="shrink-0 text-xs font-semibold">生成配置</div>
                    <div className="cursor-default" onMouseDown={(event) => event.stopPropagation()}>
                        <Segmented
                            size="small"
                            className="canvas-config-mode !rounded-md !p-0.5"
                            value={mode}
                            onChange={(value) => handleModeChange(value as CanvasGenerationMode)}
                            options={[
                                {
                                    value: "image",
                                    label: (
                                        <span className="inline-flex items-center gap-1">
                                            <ImageIcon className="size-3.5" />
                                            生图
                                        </span>
                                    ),
                                },
                                {
                                    value: "text",
                                    label: (
                                        <span className="inline-flex items-center gap-1">
                                            <MessageSquare className="size-3.5" />
                                            文本
                                        </span>
                                    ),
                                },
                                {
                                    value: "video",
                                    label: (
                                        <span className="inline-flex items-center gap-1">
                                            <Video className="size-3.5" />
                                            视频
                                        </span>
                                    ),
                                },
                                {
                                    value: "speech",
                                    label: (
                                        <span className="inline-flex items-center gap-1">
                                            <Mic2 className="size-3.5" />
                                            语音合成
                                        </span>
                                    ),
                                },
                                {
                                    value: "music",
                                    label: (
                                        <span className="inline-flex items-center gap-1">
                                            <Music2 className="size-3.5" />
                                            音乐生成
                                        </span>
                                    ),
                                },
                            ]}
                        />
                    </div>
                </div>

                <div className="mb-1.5 flex flex-wrap gap-1">
                    <InputChip label="提示词" value={`${inputSummary.textCount} 个`} style={chipStyle} />
                    <InputChip label="参考图" value={`${inputSummary.imageCount} 张`} style={chipStyle} />
                    <InputChip label="参考视频" value={`${inputSummary.videoCount} 个`} style={chipStyle} />
                    <InputChip label="参考音频" value={`${inputSummary.audioCount} 个`} style={chipStyle} />
                    <button
                        type="button"
                        className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md border px-1.5 text-[10px]"
                        style={chipStyle}
                        onMouseDown={(event) => event.stopPropagation()}
                        onClick={onComposerToggle}
                        aria-label="组装提示词"
                    >
                        <Settings2 className="size-3.5" />
                        组装提示词
                    </button>
                </div>

                <div
                    className={`mb-1.5 grid min-w-0 cursor-default items-center gap-1.5 ${mode === "image" || mode === "video" || mode === "speech" || mode === "music" ? "grid-cols-[minmax(0,1fr)_136px]" : "grid-cols-1"}`}
                    onMouseDown={(event) => event.stopPropagation()}
                >
                    <ModelPicker
                        className="canvas-compact-control h-9"
                        config={config}
                        value={config.model}
                        onChange={(model) => onConfigChange(node.id, mode === "video" ? videoModelPatch(config, model) : { model })}
                        capability={mode}
                        onMissingConfig={handleMissingConfig}
                        fullWidth
                        availableModels={requiresHostSession ? (mode === "image" ? hostImageModels : mode === "video" ? hostVideoModels : mode === "speech" ? hostSpeechModels : mode === "music" ? hostMusicModels : undefined) : undefined}
                    />
                    {mode === "video" ? (
                        <CanvasVideoSettingsPopover
                            config={config}
                            placement="topRight"
                            buttonClassName="canvas-compact-control !h-9 !w-full !justify-start !rounded-md !px-2"
                            onConfigChange={(key, value) => onConfigChange(node.id, videoConfigPatch(key, value))}
                        />
                    ) : mode === "image" ? (
                        <CanvasImageSettingsPopover
                            config={config}
                            placement="topRight"
                            autoAdjustOverflow={false}
                            buttonClassName="canvas-compact-control !h-9 !w-full !justify-start !rounded-md !px-2"
                            onConfigChange={(key, value) => onConfigChange(node.id, key === "count" ? { count: Number(value) || 1 } : { [key]: value })}
                        />
                    ) : mode === "speech" ? (
                        <CanvasAudioSettingsPopover
                            config={config}
                            placement="topRight"
                            buttonClassName="canvas-compact-control !h-9 !w-full !justify-start !rounded-md !px-2"
                            onConfigChange={(key, value) => onConfigChange(node.id, audioConfigPatch(key, value))}
                        />
                    ) : mode === "music" ? (
                        <CanvasMusicSettingsPopover config={config} placement="topRight" buttonClassName="canvas-compact-control !h-9 !w-full !justify-start !rounded-md !px-2" onConfigChange={(key, value) => onConfigChange(node.id, { [key]: value })} />
                    ) : null}
                </div>

                <Button
                    type="primary"
                    className="mt-auto !h-8 !w-full !cursor-pointer !rounded-md"
                    danger={isRunning}
                    disabled={!isRunning && !canGenerate}
                    onMouseDown={(event) => event.stopPropagation()}
                    onClick={() => (isRunning ? onStop(node.id) : onGenerate(node.id))}
                >
                    <span className="inline-flex items-center gap-1.5">
                        {isRunning ? (
                            <>
                                <LoaderCircle className="size-4 animate-spin" />
                                <Square className="size-3.5 fill-current" />
                                <span>停止</span>
                            </>
                        ) : (
                            <>
                                <span className="inline-flex items-center gap-1">
                                    <CreditSymbol />
                                    {credits.toLocaleString()}
                                </span>
                                <Play className="size-4" />
                                <span>开始生成</span>
                            </>
                        )}
                    </span>
                </Button>
            </div>
        </ConfigProvider>
    );
}

function InputChip({ label, value, style }: { label: string; value: string; style: CSSProperties }) {
    return (
        <div className="inline-flex h-6 items-center gap-1 rounded-md border px-1.5 text-[10px]" style={style}>
            <span>{label}</span>
            <span className="font-medium">{value}</span>
        </div>
    );
}

function buildNodeConfig(globalConfig: AiConfig, node: CanvasNodeData, mode: CanvasGenerationMode): AiConfig {
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
