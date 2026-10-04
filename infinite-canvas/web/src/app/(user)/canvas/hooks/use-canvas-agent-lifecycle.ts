import { useCallback, useEffect, useReducer, useRef, type RefObject } from "react";

import type { CanvasAgentMode } from "../components/canvas-agent-chat-ui";
import { CANVAS_AGENT_PANEL_MOTION_MS } from "../utils/canvas-agent-motion";

export type CanvasAgentLifecycleState = {
    mounted: boolean;
    collapsed: boolean;
    closing: boolean;
    mode: CanvasAgentMode;
};

export const INITIAL_AGENT_LIFECYCLE: CanvasAgentLifecycleState = {
    mounted: false,
    collapsed: true,
    closing: false,
    mode: "online",
};

export type CanvasAgentLifecycleAction = { type: "open"; mode?: CanvasAgentMode } | { type: "close" } | { type: "animation-complete" } | { type: "set-mode"; mode: CanvasAgentMode };

export function reduceAgentLifecycle(state: CanvasAgentLifecycleState, action: CanvasAgentLifecycleAction): CanvasAgentLifecycleState {
    if (action.type === "open") {
        return { mounted: true, collapsed: false, closing: false, mode: action.mode ?? state.mode };
    }
    if (action.type === "close") {
        return !state.mounted || state.closing ? state : { ...state, collapsed: true, closing: true };
    }
    if (action.type === "animation-complete") {
        return { ...INITIAL_AGENT_LIFECYCLE, mode: state.mode };
    }
    return action.mode === state.mode ? state : { ...state, mode: action.mode };
}

export function useCanvasAgentLifecycle({
    focusTargetRef,
    motionMs = CANVAS_AGENT_PANEL_MOTION_MS,
}: {
    focusTargetRef?: RefObject<HTMLElement | null>;
    motionMs?: number;
} = {}) {
    const [state, dispatch] = useReducer(reduceAgentLifecycle, INITIAL_AGENT_LIFECYCLE);
    const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const clearCloseTimer = useCallback(() => {
        if (!closeTimerRef.current) return;
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
    }, []);

    useEffect(() => {
        return clearCloseTimer;
    }, [clearCloseTimer]);

    const openAgent = useCallback(
        (mode?: CanvasAgentMode) => {
            clearCloseTimer();
            dispatch({ type: "open", mode });
        },
        [clearCloseTimer],
    );

    const closeAgent = useCallback(() => {
        if (!state.mounted || state.closing) return;
        dispatch({ type: "close" });
        closeTimerRef.current = setTimeout(() => {
            closeTimerRef.current = null;
            dispatch({ type: "animation-complete" });
            focusTargetRef?.current?.focus();
        }, motionMs);
    }, [focusTargetRef, motionMs, state.closing, state.mounted]);

    const toggleAgent = useCallback(
        (mode?: CanvasAgentMode) => {
            if (state.mounted && !state.collapsed && !state.closing) closeAgent();
            else openAgent(mode);
        },
        [closeAgent, openAgent, state.collapsed, state.closing, state.mounted],
    );

    const setMode = useCallback((mode: CanvasAgentMode) => dispatch({ type: "set-mode", mode }), []);

    return { ...state, openAgent, closeAgent, toggleAgent, setMode };
}
