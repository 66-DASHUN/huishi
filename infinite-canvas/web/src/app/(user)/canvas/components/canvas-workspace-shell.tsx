"use client";

import type { CSSProperties, ReactNode } from "react";

import { canvasThemes } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";

export type CanvasWorkspaceShellProps = {
    projectBar: ReactNode;
    sideRail: ReactNode;
    canvas: ReactNode;
    bottomControls: ReactNode;
    assistant: ReactNode;
    assistantOpen: boolean;
    assistantWidth: number;
    mobileToolbar: ReactNode;
    children?: ReactNode;
};

/**
 * Shared stacking context for the canvas page.
 *
 * The shell owns only placement and interaction boundaries. Content slots stay
 * opaque to it so the existing canvas, toolbar, and assistant implementations
 * can continue to own their behavior and lifecycle.
 */
export function CanvasWorkspaceShell({ projectBar, sideRail, canvas, bottomControls, assistant, assistantOpen, assistantWidth, mobileToolbar, children }: CanvasWorkspaceShellProps) {
    const theme = canvasThemes[useThemeStore((state) => state.theme)];
    const safeAssistantWidth = Number.isFinite(assistantWidth) ? Math.max(0, assistantWidth) : 0;
    const shellStyle = {
        backgroundColor: theme.canvas.background,
        color: theme.node.text,
        "--canvas-shell-border": theme.toolbar.border,
        "--canvas-shell-panel": theme.toolbar.panel,
    } as CSSProperties;
    const assistantStyle: CSSProperties = {
        // A closed drawer must not reserve space or intercept pointer input.
        width: assistantOpen ? `${safeAssistantWidth}px` : undefined,
        pointerEvents: assistantOpen ? "auto" : "none",
        borderColor: theme.toolbar.border,
        backgroundColor: theme.toolbar.panel,
        color: theme.node.text,
    };

    return (
        <main data-canvas-workspace-shell data-canvas-motion-surface className="relative flex min-h-screen min-w-0 flex-1 overflow-hidden motion-safe:transition-colors motion-reduce:transition-none" style={shellStyle}>
            <header data-canvas-project-bar className="absolute inset-x-0 top-0 z-40 min-w-0">
                {projectBar}
            </header>

            <aside data-canvas-side-rail className="relative z-30 hidden shrink-0 md:flex">
                {sideRail}
            </aside>

            <section data-canvas-viewport className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
                {canvas || children}
            </section>

            <div data-canvas-bottom-controls className="pointer-events-none absolute inset-x-0 bottom-0 z-50">
                {bottomControls}
            </div>

            <aside
                data-canvas-assistant-drawer
                aria-hidden={!assistantOpen}
                inert={!assistantOpen}
                className={`absolute inset-y-0 right-0 z-[70] hidden min-w-0 max-w-full flex-col overflow-hidden border-l motion-safe:transition-[width,opacity,transform] motion-safe:duration-200 motion-reduce:transition-none md:flex ${assistantOpen ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-2 opacity-0"}`}
                style={assistantStyle}
            >
                {assistantOpen ? assistant : null}
            </aside>

            <div data-canvas-mobile-toolbar className="pointer-events-auto absolute inset-x-0 bottom-0 z-[80] md:hidden">
                {mobileToolbar}
            </div>
        </main>
    );
}
