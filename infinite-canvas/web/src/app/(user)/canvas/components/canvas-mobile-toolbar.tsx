"use client";

import { forwardRef, useRef, useState } from "react";
import { Button, Drawer } from "antd";
import { Eraser, Ellipsis, Focus, FolderOpen, Hand, Image as ImageIcon, Keyboard, Music2, Palette, Redo2, Settings2, Type, Undo2, Upload, Video } from "lucide-react";

import { canvasThemes, type CanvasBackgroundMode } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";
import { CanvasAppearancePanel } from "./canvas-appearance-panel";

export function CanvasMobileToolbar({
    canUndo,
    canRedo,
    backgroundMode,
    showImageInfo,
    onAddImage,
    onAddVideo,
    onAddAudio,
    onAddText,
    onAddConfig,
    onUndo,
    onRedo,
    onUpload,
    onClear,
    onDeselect,
    onBackgroundModeChange,
    onShowImageInfoChange,
    onOpenMyAssets,
    onOpenShortcuts,
    onResetView,
}: {
    canUndo: boolean;
    canRedo: boolean;
    backgroundMode: CanvasBackgroundMode;
    showImageInfo: boolean;
    onAddImage: () => void;
    onAddVideo: () => void;
    onAddAudio: () => void;
    onAddText: () => void;
    onAddConfig: () => void;
    onUndo: () => void;
    onRedo: () => void;
    onUpload: () => void;
    onClear: () => void;
    onDeselect: () => void;
    onBackgroundModeChange: (mode: CanvasBackgroundMode) => void;
    onShowImageInfoChange: (show: boolean) => void;
    onOpenMyAssets: () => void;
    onOpenShortcuts: () => void;
    onResetView: () => void;
}) {
    const colorTheme = useThemeStore((state) => state.theme);
    const theme = canvasThemes[colorTheme];
    const moreButtonRef = useRef<HTMLButtonElement>(null);
    const [moreOpen, setMoreOpen] = useState(false);
    const [appearanceOpen, setAppearanceOpen] = useState(false);
    const dockStyle = { background: theme.toolbar.panel, borderColor: theme.toolbar.border, color: theme.toolbar.item };

    const closeMore = () => {
        setMoreOpen(false);
        setAppearanceOpen(false);
    };
    const runAndClose = (action: () => void) => {
        action();
        closeMore();
    };

    return (
        <>
            <nav aria-label="画布常用工具" className="pointer-events-auto absolute inset-x-0 bottom-0 z-[80] grid h-16 w-full grid-cols-5 border-t md:hidden" style={dockStyle}>
                <MobileToolButton label="选择" icon={<Hand className="size-5" />} onClick={onDeselect} />
                <MobileToolButton label="文字" icon={<Type className="size-5" />} onClick={onAddText} />
                <MobileToolButton label="图片" icon={<ImageIcon className="size-5" />} onClick={onAddImage} />
                <MobileToolButton label="上传" icon={<Upload className="size-5" />} onClick={onUpload} />
                <MobileToolButton ref={moreButtonRef} label="更多" icon={<Ellipsis className="size-5" />} aria-expanded={moreOpen} onClick={() => setMoreOpen((value) => !value)} />
            </nav>

            <Drawer
                title="更多工具"
                placement="bottom"
                height="auto"
                open={moreOpen}
                onClose={closeMore}
                afterOpenChange={(open) => {
                    if (!open) moreButtonRef.current?.focus();
                }}
                styles={{ body: { paddingTop: 4, paddingBottom: 20 }, content: { background: theme.toolbar.panel, color: theme.node.text } }}
            >
                <section aria-label="更多工具" className="grid gap-4">
                    {appearanceOpen ? (
                        <CanvasAppearancePanel backgroundMode={backgroundMode} showImageInfo={showImageInfo} onBackgroundModeChange={onBackgroundModeChange} onShowImageInfoChange={onShowImageInfoChange} onClose={() => setAppearanceOpen(false)} />
                    ) : (
                        <div className="grid grid-cols-2 gap-2">
                            <MoreAction label="撤销" icon={<Undo2 className="size-4" />} disabled={!canUndo} onClick={() => runAndClose(onUndo)} />
                            <MoreAction label="重做" icon={<Redo2 className="size-4" />} disabled={!canRedo} onClick={() => runAndClose(onRedo)} />
                            <MoreAction label="视频" icon={<Video className="size-4" />} onClick={() => runAndClose(onAddVideo)} />
                            <MoreAction label="音频" icon={<Music2 className="size-4" />} onClick={() => runAndClose(onAddAudio)} />
                            <MoreAction label="生成配置" icon={<Settings2 className="size-4" />} onClick={() => runAndClose(onAddConfig)} />
                            <MoreAction label="我的素材" icon={<FolderOpen className="size-4" />} onClick={() => runAndClose(onOpenMyAssets)} />
                            <MoreAction label="画布外观" icon={<Palette className="size-4" />} onClick={() => setAppearanceOpen(true)} />
                            <MoreAction label="快捷键" icon={<Keyboard className="size-4" />} onClick={() => runAndClose(onOpenShortcuts)} />
                            <MoreAction label="重置视图" icon={<Focus className="size-4" />} onClick={() => runAndClose(onResetView)} />
                            <MoreAction label="清空画布" icon={<Eraser className="size-4" />} danger onClick={() => runAndClose(onClear)} />
                        </div>
                    )}
                </section>
            </Drawer>
        </>
    );
}

const MobileToolButton = forwardRef<
    HTMLButtonElement,
    {
        label: string;
        icon: React.ReactNode;
        onClick: () => void;
        "aria-expanded"?: boolean;
    }
>(function MobileToolButton({ label, icon, onClick, "aria-expanded": expanded }, ref) {
    return (
        <button ref={ref} type="button" aria-label={label} aria-expanded={expanded} className="flex min-w-0 flex-col items-center justify-center gap-1 px-1 text-[11px] font-medium" onClick={onClick}>
            {icon}
            <span>{label}</span>
        </button>
    );
});

function MoreAction({ label, icon, onClick, disabled = false, danger = false }: { label: string; icon: React.ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
    return (
        <Button block disabled={disabled} danger={danger} className="!h-11 !justify-start" icon={icon} onClick={onClick}>
            {label}
        </Button>
    );
}
