"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Settings2 } from "lucide-react";
import { Button } from "antd";

import { MusicSettingsPanel, type MusicSettingKey } from "@/components/music-settings-panel";
import { canvasThemes } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";
import type { AiConfig } from "@/stores/use-config-store";

export function CanvasMusicSettingsPopover({ config, onConfigChange, buttonClassName, placement = "topLeft" }: { config: AiConfig; onConfigChange: (key: MusicSettingKey, value: string) => void; buttonClassName?: string; placement?: "topLeft" | "top" | "topRight" | "bottomLeft" | "bottom" | "bottomRight" }) {
    const theme = canvasThemes[useThemeStore((state) => state.theme)];
    const buttonRef = useRef<HTMLSpanElement>(null);
    const panelRef = useRef<HTMLDivElement>(null);
    const [open, setOpen] = useState(false);
    const [buttonRect, setButtonRect] = useState<DOMRect | null>(null);
    useEffect(() => {
        if (!open) return;
        const sync = () => setButtonRect(buttonRef.current?.getBoundingClientRect() || null);
        const outside = (event: PointerEvent) => { const target = event.target; if (target instanceof Node && !buttonRef.current?.contains(target) && !panelRef.current?.contains(target)) setOpen(false); };
        sync(); window.addEventListener("resize", sync); window.addEventListener("scroll", sync, true); window.addEventListener("pointerdown", outside, true);
        return () => { window.removeEventListener("resize", sync); window.removeEventListener("scroll", sync, true); window.removeEventListener("pointerdown", outside, true); };
    }, [open]);
    const panel = open && buttonRect ? <MusicSettingsPortal buttonRect={buttonRect} panelRef={panelRef} placement={placement} theme={theme} config={config} onConfigChange={onConfigChange} /> : null;
    return <><span ref={buttonRef} className="inline-flex min-w-0"><Button size="small" type="text" className={buttonClassName || "!h-8 !max-w-[170px] !justify-start !rounded-full !px-2.5"} style={{ background: theme.node.fill, color: theme.node.text }} icon={<Settings2 className="size-3.5" />} onClick={() => setOpen((current) => !current)}><span className="truncate">歌词 · {config.musicInstrumental === "true" ? "纯音乐" : "含人声"}</span></Button></span>{panel}</>;
}

function MusicSettingsPortal({ buttonRect, panelRef, placement, theme, config, onConfigChange }: { buttonRect: DOMRect; panelRef: RefObject<HTMLDivElement | null>; placement: "topLeft" | "top" | "topRight" | "bottomLeft" | "bottom" | "bottomRight"; theme: (typeof canvasThemes)[keyof typeof canvasThemes]; config: AiConfig; onConfigChange: (key: MusicSettingKey, value: string) => void }) {
    const width = 356; const gap = 8; const margin = 12; const alignRight = placement.endsWith("Right"); const alignCenter = placement === "top" || placement === "bottom"; const left = alignCenter ? buttonRect.left + buttonRect.width / 2 - width / 2 : alignRight ? buttonRect.right - width : buttonRect.left; const topPlacement = placement.startsWith("top");
    const style = { position: "fixed", zIndex: 1200, width, left: Math.max(margin, Math.min(window.innerWidth - width - margin, left)), ...(topPlacement ? { bottom: window.innerHeight - buttonRect.top + gap, maxHeight: Math.max(260, buttonRect.top - margin * 2) } : { top: buttonRect.bottom + gap, maxHeight: Math.max(260, window.innerHeight - buttonRect.bottom - margin * 2) }), background: theme.toolbar.panel, borderRadius: 18, boxShadow: "0 18px 54px rgba(28, 25, 23, 0.16)", padding: 18, overflowY: "auto", color: theme.node.text } as const;
    return createPortal(<div ref={panelRef} className="canvas-image-settings-popover" style={style} onPointerDown={(event) => event.stopPropagation()} onMouseDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}><MusicSettingsPanel config={config} onConfigChange={onConfigChange} theme={theme} showTitle={false} className="space-y-4" /></div>, document.body);
}
