"use client";

import { useEffect, useState } from "react";

const DESKTOP_AGENT_WIDTH = 520;

export function canvasViewportSnapshot(viewportWidth: number) {
    const width = Math.max(0, Math.round(viewportWidth));
    const compact = width < 768;
    return { compact, agentWidth: compact ? width : DESKTOP_AGENT_WIDTH };
}

export function useCanvasViewport() {
    const [viewportWidth, setViewportWidth] = useState(() => (typeof window === "undefined" ? DESKTOP_AGENT_WIDTH : window.innerWidth));

    useEffect(() => {
        const media = window.matchMedia("(max-width: 767px)");
        const update = () => setViewportWidth(window.innerWidth);
        update();
        media.addEventListener("change", update);
        window.addEventListener("resize", update);
        return () => {
            media.removeEventListener("change", update);
            window.removeEventListener("resize", update);
        };
    }, []);

    return { viewportWidth, ...canvasViewportSnapshot(viewportWidth) };
}
