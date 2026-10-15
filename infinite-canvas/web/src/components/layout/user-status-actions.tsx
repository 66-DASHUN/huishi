"use client";

import type { CSSProperties } from "react";
import { Keyboard, Settings2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { canvasThemes } from "@/lib/canvas-theme";
import { useThemeStore } from "@/stores/use-theme-store";

type UserStatusActionsProps = {
    showConfig?: boolean;
    variant?: "default" | "canvas";
    onOpenShortcuts?: () => void;
};

export function UserStatusActions({ showConfig = true, variant = "default", onOpenShortcuts }: UserStatusActionsProps) {
    const router = useRouter();
    const resolvedTheme = useThemeStore((state) => state.resolvedTheme);
    const canvasTheme = canvasThemes[resolvedTheme];
    const naturalIconClass = "inline-flex size-7 shrink-0 items-center justify-center text-foreground/65 transition hover:text-foreground [&_svg]:size-4";
    const iconStyle: CSSProperties | undefined = variant === "canvas" ? { color: canvasTheme.node.text } : undefined;

    return (
        <div className="inline-flex shrink-0 items-center gap-1">
            {showConfig ? (
                <button type="button" className={naturalIconClass} style={iconStyle} onClick={() => router.push("/settings")} aria-label="配置" title="配置">
                    <Settings2 className="size-4" />
                </button>
            ) : null}
            {onOpenShortcuts ? (
                <button type="button" className={naturalIconClass} style={iconStyle} onClick={onOpenShortcuts} aria-label="快捷键" title="快捷键">
                    <Keyboard className="size-4" />
                </button>
            ) : null}
        </div>
    );
}
