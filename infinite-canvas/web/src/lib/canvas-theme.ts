export type CanvasColorTheme = "light" | "dark";
export type CanvasBackgroundMode = "dots" | "lines" | "blank";

export const canvasThemes = {
    light: {
        canvas: {
            background: "#f8f9fb",
            dot: "rgba(67,76,91,.25)",
            line: "rgba(67,76,91,.12)",
            selectionStroke: "#2f6bff",
            selectionFill: "rgba(47,107,255,.08)",
        },
        node: {
            label: "#596272",
            fill: "#f3f5f8",
            panel: "#ffffff",
            stroke: "#e2e6ec",
            activeStroke: "#2f6bff",
            placeholder: "#8a93a2",
            text: "#252a32",
            muted: "#667184",
            faint: "#9aa3b0",
        },
        toolbar: {
            panel: "rgba(255,255,255,.96)",
            border: "#e2e6ec",
            item: "#596272",
            itemHover: "#f3f5f8",
            activeBg: "#edf2ff",
            activeText: "#2f6bff",
        },
    },
    dark: {
        canvas: {
            background: "#111317",
            dot: "rgba(225,230,238,.22)",
            line: "rgba(225,230,238,.10)",
            selectionStroke: "#85a9ff",
            selectionFill: "rgba(133,169,255,.12)",
        },
        node: {
            label: "#c3cad5",
            fill: "#20242b",
            panel: "#1a1e24",
            stroke: "#343a45",
            activeStroke: "#85a9ff",
            placeholder: "#8d96a5",
            text: "#f4f6f9",
            muted: "#b5bdc9",
            faint: "#737d8d",
        },
        toolbar: {
            panel: "rgba(26,30,36,.96)",
            border: "#343a45",
            item: "#c3cad5",
            itemHover: "#252a32",
            activeBg: "#263451",
            activeText: "#a9c1ff",
        },
    },
} as const;

export type CanvasTheme = (typeof canvasThemes)[CanvasColorTheme];
