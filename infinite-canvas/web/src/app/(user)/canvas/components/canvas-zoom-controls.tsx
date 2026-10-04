import { Map, MousePointer2, Waypoints } from "lucide-react";
import { Button, Tooltip } from "antd";

import { canvasThemes } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";

type CanvasZoomControlsProps = {
    scale: number;
    onSelect: () => void;
    isMiniMapOpen: boolean;
    onToggleMiniMap: () => void;
    showConnections: boolean;
    onToggleConnections: () => void;
};

export function CanvasZoomControls({ scale, onSelect, isMiniMapOpen, onToggleMiniMap, showConnections, onToggleConnections }: CanvasZoomControlsProps) {
    const colorTheme = useThemeStore((state) => state.theme);
    const theme = canvasThemes[colorTheme];
    const dockStyle = { background: theme.toolbar.panel, borderColor: theme.toolbar.border, color: theme.toolbar.item, boxShadow: colorTheme === "dark" ? "none" : "0 2px 8px rgb(16 24 40 / 6%)" };
    const activeStyle = { background: theme.toolbar.itemHover, color: theme.node.text };
    const idleStyle = { color: theme.toolbar.item };

    return (
        <div className="pointer-events-auto min-w-0" onMouseDown={(event) => event.stopPropagation()} onPointerDown={(event) => event.stopPropagation()}>
            <div className="flex h-11 items-center gap-1 rounded-xl border p-1" style={dockStyle}>
                <Tooltip title="选择工具">
                    <Button aria-label="选择工具" type="text" className="!h-9 !w-9 !min-w-9 !p-0" style={activeStyle} onClick={onSelect} icon={<MousePointer2 className="size-4" />} />
                </Tooltip>
                <Tooltip title="小地图">
                    <Button aria-label="小地图" aria-pressed={isMiniMapOpen} type="text" className="!h-9 !w-9 !min-w-9 !p-0" style={isMiniMapOpen ? activeStyle : idleStyle} onClick={onToggleMiniMap} icon={<Map className="size-4" />} />
                </Tooltip>
                <Tooltip title="显示连线">
                    <Button aria-label="显示连线" aria-pressed={showConnections} type="text" className="!h-9 !w-9 !min-w-9 !p-0" style={showConnections ? activeStyle : idleStyle} onClick={onToggleConnections} icon={<Waypoints className="size-4" />} />
                </Tooltip>
                <span className="mx-1 h-4 w-px" style={{ background: theme.toolbar.border }} />
                <span className="min-w-12 px-1 text-center text-xs tabular-nums" style={{ color: theme.node.muted }}>
                    {Math.round(scale * 100)}%
                </span>
            </div>
        </div>
    );
}
