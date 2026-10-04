"use client";

import { Button, Segmented, Switch } from "antd";
import { CircleDot, Grid2x2, Info, Square } from "lucide-react";

import { canvasThemes, type CanvasBackgroundMode } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";

export function CanvasAppearancePanel({
    backgroundMode,
    showImageInfo,
    onBackgroundModeChange,
    onShowImageInfoChange,
    onClose,
}: {
    backgroundMode: CanvasBackgroundMode;
    showImageInfo: boolean;
    onBackgroundModeChange: (mode: CanvasBackgroundMode) => void;
    onShowImageInfoChange: (show: boolean) => void;
    onClose?: () => void;
}) {
    const colorTheme = useThemeStore((state) => state.theme);
    const theme = canvasThemes[colorTheme];

    return (
        <section aria-label="画布外观" className="grid gap-3">
            <div className="text-sm font-medium opacity-65">画布外观</div>
            <div>
                <div className="pb-1.5 text-[11px] font-medium opacity-50">网格样式</div>
                <Segmented
                    block
                    className="!p-1 [&_.ant-segmented-group]:!flex [&_.ant-segmented-item]:!min-h-8 [&_.ant-segmented-item]:!flex-1 [&_.ant-segmented-item-label]:!min-h-8 [&_.ant-segmented-item-label]:!leading-8"
                    value={backgroundMode}
                    onChange={(value) => onBackgroundModeChange(value as CanvasBackgroundMode)}
                    options={[
                        {
                            value: "dots",
                            label: (
                                <span className="inline-flex items-center gap-1.5">
                                    <CircleDot className="size-4" />点
                                </span>
                            ),
                        },
                        {
                            value: "lines",
                            label: (
                                <span className="inline-flex items-center gap-1.5">
                                    <Grid2x2 className="size-4" />线
                                </span>
                            ),
                        },
                        {
                            value: "blank",
                            label: (
                                <span className="inline-flex items-center gap-1.5">
                                    <Square className="size-4" />
                                    空白
                                </span>
                            ),
                        },
                    ]}
                />
            </div>
            <div className="flex items-center justify-between gap-3 rounded-lg px-1.5 py-1">
                <span className="inline-flex min-w-0 items-center gap-1.5 text-[11px] font-medium opacity-65">
                    <Info className="size-3.5" />
                    图片信息
                </span>
                <Switch size="small" checked={showImageInfo} onChange={onShowImageInfoChange} />
            </div>
            {onClose ? (
                <Button type="text" onClick={onClose}>
                    完成
                </Button>
            ) : null}
        </section>
    );
}
