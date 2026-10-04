"use client";

import { type ReactNode } from "react";

import { ImageSettingsTheme } from "@/components/image-settings-panel";
import type { CanvasTheme } from "@/lib/canvas-theme";
import type { AiConfig } from "@/stores/use-config-store";

export type MusicSettingKey = "musicLyrics" | "musicInstrumental" | "musicReferenceUrl";

export function MusicSettingsPanel({ config, onConfigChange, theme, showTitle = true, className = "w-[320px] space-y-4 rounded-2xl px-1 py-0.5" }: { config: AiConfig; onConfigChange: (key: MusicSettingKey, value: string) => void; theme: CanvasTheme; showTitle?: boolean; className?: string }) {
    return (
        <ImageSettingsTheme theme={theme}>
            <div className={className} style={{ color: theme.node.text }} onMouseDown={(event) => event.stopPropagation()}>
                {showTitle ? <div className="text-lg font-semibold">音乐设置</div> : null}
                <SettingGroup title="歌词" color={theme.node.muted}>
                    <textarea value={config.musicLyrics || ""} placeholder="可选：输入歌词，留空则按描述生成。" className="h-24 w-full resize-none rounded-xl border bg-transparent px-3 py-2 text-sm leading-5 outline-none" style={{ borderColor: theme.node.stroke, color: theme.node.text }} onChange={(event) => onConfigChange("musicLyrics", event.target.value)} onMouseDown={(event) => event.stopPropagation()} />
                </SettingGroup>
                <SettingGroup title="人声" color={theme.node.muted}>
                    <div className="grid grid-cols-2 gap-2">
                        {[{ value: "false", label: "含人声" }, { value: "true", label: "纯音乐" }].map((item) => (
                            <button key={item.value} type="button" className="h-9 cursor-pointer rounded-full border px-2 text-sm transition hover:opacity-80" style={{ borderColor: config.musicInstrumental === item.value ? theme.node.text : theme.node.stroke, color: theme.node.text }} onMouseDown={(event) => event.stopPropagation()} onClick={() => onConfigChange("musicInstrumental", item.value)}>{item.label}</button>
                        ))}
                    </div>
                </SettingGroup>
                <SettingGroup title="参考音频" color={theme.node.muted}>
                    <input value={config.musicReferenceUrl || ""} placeholder="可选：参考音频 URL" className="h-9 w-full rounded-xl border bg-transparent px-3 text-sm outline-none" style={{ borderColor: theme.node.stroke, color: theme.node.text }} onChange={(event) => onConfigChange("musicReferenceUrl", event.target.value)} onMouseDown={(event) => event.stopPropagation()} />
                </SettingGroup>
            </div>
        </ImageSettingsTheme>
    );
}

function SettingGroup({ title, color, children }: { title: string; color: string; children: ReactNode }) {
    return <div className="space-y-2.5"><div className="text-xs font-medium" style={{ color }}>{title}</div>{children}</div>;
}
