"use client";

import { ArrowLeft, CloudOff, LoaderCircle, RotateCcw } from "lucide-react";

export type CanvasStatus = "session" | "project" | "offline" | "error";

export const CANVAS_STATUS_COPY: Record<CanvasStatus, { title: string; description: string; action: string }> = {
    session: {
        title: "正在连接画布",
        description: "正在校验主站会话和工作区权限。",
        action: "重新连接",
    },
    project: {
        title: "画布加载失败",
        description: "本地画布没有被改动，请重新加载。",
        action: "重试加载",
    },
    offline: {
        title: "网络连接已断开",
        description: "本地画布仍会保留，重新联网后可以继续。",
        action: "重试连接",
    },
    error: {
        title: "无法打开画布",
        description: "这个画布可能已被删除，或只保存在其他浏览器中。",
        action: "返回画布列表",
    },
};

type CanvasStatusScreenProps = {
    status: CanvasStatus;
    loading?: boolean;
    title?: string;
    description?: string;
    actionLabel?: string;
    onAction?: () => void;
};

export function CanvasStatusScreen({ status, loading = false, title, description, actionLabel, onAction }: CanvasStatusScreenProps) {
    const copy = CANVAS_STATUS_COPY[status];
    const StatusIcon = loading ? LoaderCircle : status === "offline" ? CloudOff : status === "error" ? ArrowLeft : RotateCcw;
    const ActionIcon = status === "error" ? ArrowLeft : RotateCcw;
    const handleAction = onAction || (() => window.location.reload());

    return (
        <main role={loading ? "status" : "alert"} aria-live={loading ? "polite" : "assertive"} data-canvas-status={status} className="relative grid h-full min-h-0 place-items-center overflow-hidden bg-background px-6 text-foreground">
            <div className="flex max-w-sm flex-col items-center text-center">
                <StatusIcon className={`mb-5 size-6 text-stone-500 ${loading ? "animate-spin" : ""}`} strokeWidth={1.8} aria-hidden="true" />
                <h1 className="text-lg font-semibold">{title || copy.title}</h1>
                <p className="mt-2 text-sm leading-6 text-stone-500 dark:text-stone-400">{description || copy.description}</p>
                <button
                    type="button"
                    className="mt-6 inline-flex h-9 items-center gap-2 rounded-md border border-stone-300 bg-white px-3.5 text-sm font-medium text-stone-800 shadow-sm transition hover:bg-stone-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:hover:bg-stone-800"
                    onClick={handleAction}
                >
                    <ActionIcon className="size-4" aria-hidden="true" />
                    {actionLabel || copy.action}
                </button>
            </div>
        </main>
    );
}
