"use client";

import { Check, Download, Pencil, Trash2, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Input, Tooltip } from "antd";

import { useCanvasStore, type CanvasProject } from "../stores/use-canvas-store";
import { useCanvasUiStore } from "../stores/use-canvas-ui-store";
import { exportCanvasProjects } from "../utils/canvas-export";
import { withBasePath } from "@/lib/app-path";

export function CanvasProjectCard({ project }: { project: CanvasProject }) {
    const router = useRouter();
    const searchParams = useSearchParams();
    const renameProject = useCanvasStore((state) => state.renameProject);
    const selectedIds = useCanvasUiStore((state) => state.selectedProjectIds);
    const editingId = useCanvasUiStore((state) => state.editingProjectId);
    const editingTitle = useCanvasUiStore((state) => state.editingProjectTitle);
    const startEditing = useCanvasUiStore((state) => state.startEditingProject);
    const setEditingTitle = useCanvasUiStore((state) => state.setEditingProjectTitle);
    const stopEditing = useCanvasUiStore((state) => state.stopEditingProject);
    const toggleSelected = useCanvasUiStore((state) => state.toggleSelectedProjectId);
    const setDeleteIds = useCanvasUiStore((state) => state.setDeleteProjectIds);
    const editing = editingId === project.id;
    const selected = selectedIds.includes(project.id);
    const open = () => router.push(withBasePath(`/canvas/${project.id}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`));
    const saveTitle = () => {
        renameProject(project.id, editingTitle);
        stopEditing();
    };

    return (
        <article className="group flex cursor-pointer flex-col justify-between rounded-lg border border-border bg-card p-4 text-card-foreground shadow-xs transition-[border-color,box-shadow] hover:border-primary/35 hover:shadow-sm" onClick={() => !editing && open()}>
            <div className="flex items-start gap-3">
                <input
                    type="checkbox"
                    checked={selected}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => toggleSelected(project.id, event.target.checked)}
                    className={`mt-1 size-4 accent-primary transition-opacity ${selected ? "opacity-100" : "opacity-35 group-hover:opacity-100 group-focus-within:opacity-100"}`}
                    aria-label={`选择 ${project.title}`}
                />
                {editing ? (
                    <Input className="min-w-0" value={editingTitle} onClick={(event) => event.stopPropagation()} onChange={(event) => setEditingTitle(event.target.value)} onKeyDown={(event) => event.key === "Enter" && saveTitle()} autoFocus />
                ) : (
                    <button
                        type="button"
                        className="min-w-0 cursor-pointer text-left"
                        onClick={(event) => {
                            event.stopPropagation();
                            open();
                        }}
                    >
                        <h2 className="truncate text-base font-semibold">{project.title}</h2>
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                            {project.nodes.length} 个节点 · {project.connections.length} 条连线
                        </p>
                    </button>
                )}
            </div>
            <div className="mt-5 flex items-end justify-between gap-3">
                <p className="text-xs text-muted-foreground">更新于 {new Date(project.updatedAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</p>
                <div className="flex items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100" onClick={(event) => event.stopPropagation()}>
                    {editing ? (
                        <>
                            <Tooltip title="保存名称"><Button type="text" size="small" shape="circle" icon={<Check className="size-4" />} onClick={saveTitle} aria-label="保存名称" /></Tooltip>
                            <Tooltip title="取消重命名"><Button type="text" size="small" shape="circle" icon={<X className="size-4" />} onClick={stopEditing} aria-label="取消重命名" /></Tooltip>
                        </>
                    ) : (
                        <>
                            <Tooltip title="导出"><Button type="text" size="small" shape="circle" icon={<Download className="size-4" />} onClick={() => void exportCanvasProjects([project], project.title || "无限画布")} aria-label="导出" /></Tooltip>
                            <Tooltip title="重命名"><Button type="text" size="small" shape="circle" icon={<Pencil className="size-4" />} onClick={() => startEditing(project.id, project.title)} aria-label="重命名" /></Tooltip>
                            <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
                            <Tooltip title="删除"><Button type="text" size="small" shape="circle" className="!text-destructive" icon={<Trash2 className="size-4" />} onClick={() => setDeleteIds([project.id])} aria-label="删除" /></Tooltip>
                        </>
                    )}
                </div>
            </div>
        </article>
    );
}
