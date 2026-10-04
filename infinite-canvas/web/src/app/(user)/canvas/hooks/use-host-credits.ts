"use client";

import { useEffect, useRef, useState } from "react";
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";
import { requestHostEstimate } from "@/services/api/host-image";

/**
 * 统一画布积分估算 hook。
 * 嵌入主站时调用 /api/canvas/estimate 获取真实积分消耗；
 * 独立模式下返回 null（由调用方降级到本地 requestCreditCost）。
 */
export function useHostCredits(opts: { model?: string; resolution?: string; count?: number; enabled?: boolean }): number | null {
    const hostGenerateUrl = useCanvasHostSessionStore((state) => state.generateUrl);
    const hostToken = useCanvasHostSessionStore((state) => state.token);
    const [credits, setCredits] = useState<number | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    const { resolution = "2K", count = 1, enabled = true } = opts;

    useEffect(() => {
        if (!enabled || !hostGenerateUrl || !hostToken) {
            abortRef.current?.abort("host estimate disabled");
            abortRef.current = null;
            setCredits(null);
            return;
        }
        abortRef.current?.abort("host estimate superseded");
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        requestHostEstimate({ generateUrl: hostGenerateUrl, token: hostToken }, { model: opts.model, resolution, count: Math.max(1, count), signal: ctrl.signal })
            .then((res) => {
                if (!ctrl.signal.aborted) setCredits(res.cost);
            })
            .catch((err) => {
                if (ctrl.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
                if (!ctrl.signal.aborted) setCredits(null);
            });
        return () => {
            ctrl.abort("host estimate cleanup");
            if (abortRef.current === ctrl) abortRef.current = null;
        };
    }, [enabled, hostGenerateUrl, hostToken, opts.model, resolution, count]);

    return credits;
}
