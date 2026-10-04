export type CanvasToolId = "hand" | "undo" | "redo" | "text" | "image" | "video" | "audio" | "config" | "upload" | "assets" | "appearance" | "shortcuts" | "reset" | "clear" | "more";

export const MOBILE_PRIMARY_TOOL_IDS = ["hand", "text", "image", "upload", "more"] as const satisfies readonly CanvasToolId[];

export const MOBILE_MORE_TOOL_IDS = ["undo", "redo", "video", "audio", "config", "assets", "appearance", "shortcuts", "reset", "clear"] as const satisfies readonly CanvasToolId[];

export const DESKTOP_PRIMARY_TOOL_IDS = ["hand", "undo", "redo", "text", "image", "video", "config", "upload", "appearance", "more"] as const satisfies readonly CanvasToolId[];

export const DESKTOP_MORE_TOOL_IDS = ["audio", "assets", "shortcuts", "reset", "clear"] as const satisfies readonly CanvasToolId[];
