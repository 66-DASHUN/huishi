"use client";

export const CANVAS_GENERATION_LEAVE_MESSAGE = "画布正在生成，离开当前页面会中断本次生成。确定要离开吗？";

export function confirmCanvasNavigation(isGenerating: boolean) {
    if (!isGenerating) return true;
    if (typeof window === "undefined") return false;
    return window.confirm(CANVAS_GENERATION_LEAVE_MESSAGE);
}

export function navigateFromCanvas(href: string, isGenerating: boolean) {
    if (typeof window === "undefined") return;
    if (!confirmCanvasNavigation(isGenerating)) return;
    window.location.href = href;
}
