import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode, RefObject } from "react";
import { useRef, useState } from "react";
import { Button, Popover } from "antd";
import { BotMessageSquare, Ellipsis, Eraser, Focus, FolderOpen, Hand, Image as ImageIcon, Keyboard, Music2, Palette, Redo2, Settings2, Trash2, Type, Undo2, Upload, Video } from "lucide-react";

import { canvasThemes, type CanvasBackgroundMode, type CanvasTheme } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";
import { CanvasAppearancePanel } from "./canvas-appearance-panel";
import { CanvasMobileToolbar } from "./canvas-mobile-toolbar";

export function CanvasToolbar({
    selectedCount,
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
    onDelete,
    onClear,
    onDeselect,
    onBackgroundModeChange,
    onShowImageInfoChange,
    onOpenMyAssets,
    onOpenShortcuts,
    onResetView,
    onOpenAssistant,
    agentOpen = false,
    zoomControls,
    renderMobileToolbar = true,
    hostEmbedded = false,
}: {
    selectedCount: number;
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
    onDelete: () => void;
    onClear: () => void;
    onDeselect: () => void;
    onBackgroundModeChange: (mode: CanvasBackgroundMode) => void;
    onShowImageInfoChange: (show: boolean) => void;
    onOpenMyAssets: () => void;
    onOpenShortcuts: () => void;
    onResetView: () => void;
    onOpenAssistant?: () => void;
    agentOpen?: boolean;
    zoomControls: ReactNode | null;
    renderMobileToolbar?: boolean;
    /** 嵌入主站 iframe 模式，工具栏从全宽居中而非偏移左侧面板 */
    hostEmbedded?: boolean;
}) {
    const wrapRef = useRef<HTMLDivElement>(null);
    const colorTheme = useThemeStore((state) => state.theme);
    const theme = canvasThemes[colorTheme];
    const [hovered, setHovered] = useState<string | null>(null);
    const [tipY, setTipY] = useState(0);
    const [appearanceOpen, setAppearanceOpen] = useState(false);
    const [moreOpen, setMoreOpen] = useState(false);
    const dockStyle = { background: theme.toolbar.panel, borderColor: theme.toolbar.border, color: theme.toolbar.item };
    const hoverStyle = { background: theme.toolbar.itemHover, color: theme.node.text };
    const activeStyle = { background: theme.toolbar.itemHover, color: theme.node.text };
    const tip = hovered ? toolLabel(hovered) : "";
    const runMoreAction = (action: () => void) => {
        setMoreOpen(false);
        action();
    };
    const moreTools = (
        <div data-canvas-more-tools className="grid w-40 gap-1 p-1">
            <Button type="text" className="!justify-start" icon={<Music2 className="size-4" />} onClick={() => runMoreAction(onAddAudio)}>
                添加音频
            </Button>
            <Button type="text" className="!justify-start" icon={<FolderOpen className="size-4" />} onClick={() => runMoreAction(onOpenMyAssets)}>
                我的素材
            </Button>
            <Button type="text" className="!justify-start" icon={<Keyboard className="size-4" />} onClick={() => runMoreAction(onOpenShortcuts)}>
                快捷键
            </Button>
            <Button type="text" className="!justify-start" icon={<Focus className="size-4" />} onClick={() => runMoreAction(onResetView)}>
                重置视图
            </Button>
            <Button type="text" danger className="!justify-start" icon={<Eraser className="size-4" />} onClick={() => runMoreAction(onClear)}>
                清空画布
            </Button>
        </div>
    );

    return (
        <>
            <nav data-canvas-side-tools aria-label="画布工具" className="pointer-events-auto absolute left-4 top-1/2 z-[60] hidden w-14 -translate-y-1/2 items-center gap-1 rounded-xl border px-2 py-2.5 md:flex md:flex-col" style={dockStyle}>
                <div ref={wrapRef} className="relative flex flex-col items-center gap-1">
                    {tip ? <DockTip label={tip} theme={theme} top={tipY} /> : null}
                    <ToolbarButton id="tool-hand" label="移动/选择" active={!selectedCount} hovered={hovered} activeStyle={activeStyle} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onDeselect}>
                        <Hand className="size-4.5" />
                    </ToolbarButton>
                    <ToolbarButton id="tool-undo" label="撤销" disabled={!canUndo} hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onUndo}>
                        <Undo2 className="size-4.5" />
                    </ToolbarButton>
                    <ToolbarButton id="tool-redo" label="重做" disabled={!canRedo} hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onRedo}>
                        <Redo2 className="size-4.5" />
                    </ToolbarButton>
                    <Divider theme={theme} />
                    <ToolbarButton id="tool-text" label="文本" hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onAddText}>
                        <Type className="size-4.5" />
                    </ToolbarButton>
                    <ToolbarButton id="tool-image" label="图片" hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onAddImage}>
                        <ImageIcon className="size-4.5" />
                    </ToolbarButton>
                    <ToolbarButton id="tool-video" label="视频" hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onAddVideo}>
                        <Video className="size-4.5" />
                    </ToolbarButton>
                    <ToolbarButton id="tool-config" label="生成配置" hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onAddConfig}>
                        <Settings2 className="size-4.5" />
                    </ToolbarButton>
                    <ToolbarButton id="tool-upload" label="上传素材" hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onUpload}>
                        <Upload className="size-4.5" />
                    </ToolbarButton>
                    {hostEmbedded && onOpenAssistant ? (
                        <>
                            <Divider theme={theme} />
                            <ToolbarButton id="tool-assistant" label="画布助手" active={agentOpen} hovered={hovered} activeStyle={activeStyle} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onOpenAssistant}>
                                <BotMessageSquare className="size-4.5" />
                            </ToolbarButton>
                        </>
                    ) : null}
                    <ToolbarButton
                        id="tool-style"
                        label="画布外观"
                        active={appearanceOpen}
                        hovered={hovered}
                        activeStyle={activeStyle}
                        hoverStyle={hoverStyle}
                        wrapRef={wrapRef}
                        onTipY={setTipY}
                        onHover={setHovered}
                        onClick={() => setAppearanceOpen((value) => !value)}
                    >
                        <Palette className="size-4.5" />
                    </ToolbarButton>
                    {selectedCount ? (
                        <>
                            <Divider theme={theme} />
                            <ToolbarButton id="tool-delete" label="删除选中" hovered={hovered} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered} onClick={onDelete} danger>
                                <Trash2 className="size-4.5" />
                            </ToolbarButton>
                        </>
                    ) : null}
                    <Popover content={moreTools} trigger="click" placement="rightTop" arrow={false} open={moreOpen} onOpenChange={setMoreOpen}>
                        <ToolbarButton id="tool-more" label="更多工具" active={moreOpen} hovered={hovered} activeStyle={activeStyle} hoverStyle={hoverStyle} wrapRef={wrapRef} onTipY={setTipY} onHover={setHovered}>
                            <Ellipsis className="size-4.5" />
                        </ToolbarButton>
                    </Popover>
                </div>
                {appearanceOpen ? (
                    <div className="pointer-events-auto absolute left-[calc(100%+8px)] top-0 z-30 w-[248px] rounded-lg border p-3" style={{ background: theme.toolbar.panel, borderColor: theme.toolbar.border, color: theme.toolbar.item }}>
                        <CanvasAppearancePanel backgroundMode={backgroundMode} showImageInfo={showImageInfo} onBackgroundModeChange={onBackgroundModeChange} onShowImageInfoChange={onShowImageInfoChange} />
                    </div>
                ) : null}
            </nav>
            {renderMobileToolbar ? (
                <CanvasMobileToolbar
                    canUndo={canUndo}
                    canRedo={canRedo}
                    backgroundMode={backgroundMode}
                    showImageInfo={showImageInfo}
                    onAddImage={onAddImage}
                    onAddVideo={onAddVideo}
                    onAddAudio={onAddAudio}
                    onAddText={onAddText}
                    onAddConfig={onAddConfig}
                    onUndo={onUndo}
                    onRedo={onRedo}
                    onUpload={onUpload}
                    onClear={onClear}
                    onDeselect={onDeselect}
                    onBackgroundModeChange={onBackgroundModeChange}
                    onShowImageInfoChange={onShowImageInfoChange}
                    onOpenMyAssets={onOpenMyAssets}
                    onOpenShortcuts={onOpenShortcuts}
                    onResetView={onResetView}
                />
            ) : null}
        </>
    );
}

function ToolbarButton({
    id,
    label,
    active,
    hovered,
    activeStyle,
    hoverStyle,
    wrapRef,
    onTipY,
    onHover,
    onClick,
    disabled = false,
    danger = false,
    children,
}: {
    id: string;
    label: string;
    active?: boolean;
    hovered: string | null;
    activeStyle?: CSSProperties;
    hoverStyle: CSSProperties;
    wrapRef: RefObject<HTMLDivElement | null>;
    onTipY: (y: number) => void;
    onHover: (id: string | null) => void;
    onClick?: (event: ReactMouseEvent<HTMLElement>) => void;
    disabled?: boolean;
    danger?: boolean;
    children: ReactNode;
}) {
    const theme = canvasThemes[useThemeStore((state) => state.theme)];

    return (
        <Button
            type="text"
            aria-label={label}
            className="!h-8 !w-8 !min-w-8 !p-0"
            disabled={disabled}
            style={active ? activeStyle : hovered === id && !disabled ? hoverStyle : { color: danger ? "#f87171" : theme.toolbar.item, opacity: disabled ? 0.35 : 1 }}
            icon={children}
            onMouseEnter={(event) => {
                onHover(id);
                onTipY(getTipY(wrapRef.current, event.currentTarget));
            }}
            onMouseLeave={() => onHover(null)}
            onClick={onClick}
        />
    );
}

function Divider({ theme }: { theme: CanvasTheme }) {
    return <div className="mx-0.5 h-px w-6" style={{ background: theme.toolbar.border }} />;
}

function DockTip({ label, theme, top }: { label: string; theme: CanvasTheme; top: number }) {
    return (
        <span className="pointer-events-none absolute left-[calc(100%+8px)] z-20 -translate-y-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs" style={{ top, background: theme.node.text, color: theme.node.panel }}>
            {label}
        </span>
    );
}

function toolLabel(id: string) {
    if (id === "tool-hand") return "移动/选择";
    if (id === "tool-undo") return "撤销";
    if (id === "tool-redo") return "重做";
    if (id === "tool-text") return "文本";
    if (id === "tool-image") return "图片";
    if (id === "tool-video") return "视频";
    if (id === "tool-audio") return "音频";
    if (id === "tool-config") return "生成配置";
    if (id === "tool-upload") return "上传素材";
    if (id === "tool-assets") return "我的素材";
    if (id === "tool-assistant") return "画布助手";
    if (id === "tool-style") return "画布外观";
    if (id === "tool-delete") return "删除选中";
    if (id === "tool-clear") return "清空画布";
    if (id === "tool-more") return "更多工具";
    return "";
}

function getTipY(wrap: HTMLDivElement | null, target: HTMLElement) {
    if (!wrap) return 0;
    const wrapBox = wrap.getBoundingClientRect();
    const box = target.getBoundingClientRect();
    return box.top - wrapBox.top + box.height / 2;
}
