"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { App, Button } from "antd";
import { Download, FileUp, Plus } from "lucide-react";

import { readZip } from "@/lib/zip";
import { setMediaBlob } from "@/services/file-storage";
import { setImageBlob } from "@/services/image-storage";
import { withBasePath } from "@/lib/app-path";
import { CanvasDeleteProjectsDialog } from "./components/canvas-delete-projects-dialog";
import { CanvasHostSessionGuard } from "./components/canvas-host-session-guard";
import { CanvasProjectCard } from "./components/canvas-project-card";
import type { CanvasExportFile } from "./export-types";
import { useCanvasStore } from "./stores/use-canvas-store";
import { useCanvasUiStore } from "./stores/use-canvas-ui-store";
import { exportCanvasProjects } from "./utils/canvas-export";
import { nextCanvasProjectTitle } from "./utils/canvas-project-title";
import { readHostSessionToken } from "./lib/host-canvas-session";

export default function CanvasPage() {
    return (
        <Suspense fallback={<CanvasSessionLoading />}>
            <CanvasHostSessionGuard>
                <CanvasProjectsPage />
            </CanvasHostSessionGuard>
        </Suspense>
    );
}

function CanvasSessionLoading() {
    return <main className="flex h-full items-center justify-center text-sm text-stone-500">会话校验中...</main>;
}

function CanvasProjectsPage() {
    const { message } = App.useApp();
    const router = useRouter();
    const searchParams = useSearchParams();
    const inputRef = useRef<HTMLInputElement>(null);
    const autoOpenRef = useRef(false);
    const hydrated = useCanvasStore((state) => state.hydrated);
    const projects = useCanvasStore((state) => state.projects);
    const createProject = useCanvasStore((state) => state.createProject);
    const importProject = useCanvasStore((state) => state.importProject);
    const selectedIds = useCanvasUiStore((state) => state.selectedProjectIds);
    const setDeleteIds = useCanvasUiStore((state) => state.setDeleteProjectIds);

    const mode = searchParams.get("mode");
    const hostEmbedded = searchParams.get("host_mode") === "huishi";
    const effectiveMode = mode || (hostEmbedded ? "recent" : null);
    const agentMode = effectiveMode === "recent" || effectiveMode === "choose";
    const hostSessionQuery = useMemo(() => {
        const query = new URLSearchParams();
        ["host_mode", "host_session_token", "host_session_verify_url", "host_assets_library_url", "host_generate_url", "host_video_tasks_url", "host_chat_url", "host_projects_url", "host_user_key_url", "host_user_key_enabled", "host_origin"].forEach((key) => {
            const value = searchParams.get(key);
            if (value) query.set(key, value);
        });
        return query.toString();
    }, [searchParams]);
    const agentQuery = agentMode ? `?${searchParams.toString()}` : hostSessionQuery ? `?${hostSessionQuery}` : "";
    // The host session token lives in the URL fragment, which a client-side
    // route change does not carry over on its own. Forward it explicitly so the
    // project page can still establish the host session.
    const hostSessionFragment = useMemo(() => {
        const token = readHostSessionToken();
        return token ? `#host_session_token=${encodeURIComponent(token)}` : "";
    }, []);
    const enterProject = useCallback(
        (id: string) => {
            router.push(withBasePath(`/canvas/${id}${agentQuery}${hostSessionFragment}`));
        },
        [agentQuery, hostSessionFragment, router],
    );
    const createProjectAndStay = () => {
        createProject(nextCanvasProjectTitle(projects, "新建画布"));
    };
    const importCanvas = async (file?: File) => {
        if (!file) return;
        try {
            const zip = await readZip(file);
            const projectFile = zip.get("projects.json");
            if (!projectFile) throw new Error("missing projects.json");
            const data = JSON.parse(await projectFile.text()) as CanvasExportFile;
            await Promise.all(
                data.projects.flatMap((project) =>
                    project.files.map(async (item) => {
                        const blob = zip.get(item.path);
                        if (!blob) return;
                        const typedBlob = blob.type ? blob : blob.slice(0, blob.size, item.mimeType);
                        await (item.storageKey.startsWith("image:") ? setImageBlob(item.storageKey, typedBlob) : setMediaBlob(item.storageKey, typedBlob));
                    }),
                ),
            );
            data.projects.forEach((item) => importProject(item.project));
            message.success(`已导入 ${data.projects.length} 个画布`);
        } catch {
            message.error("导入失败，请选择有效的画布压缩包");
        } finally {
            if (inputRef.current) inputRef.current.value = "";
        }
    };

    useEffect(() => {
        // 嵌入模式下不自动跳转，保留项目列表让用户选择
        if (hostEmbedded) return;
        if (effectiveMode === "new") {
            if (!hydrated || autoOpenRef.current) return;
            autoOpenRef.current = true;
            createProject(nextCanvasProjectTitle(projects, "新建画布"));
            router.replace(withBasePath(`/canvas${hostSessionQuery ? `?${hostSessionQuery}` : ""}`));
            return;
        }
        if (!hydrated || autoOpenRef.current || effectiveMode !== "recent") return;
        autoOpenRef.current = true;
        enterProject(projects[0]?.id || createProject(nextCanvasProjectTitle(projects, "新建画布")));
    }, [createProject, effectiveMode, enterProject, hostEmbedded, hostSessionQuery, hydrated, projects, router]);

    if (!hostEmbedded && hydrated && effectiveMode === "recent") return <main className="flex h-full items-center justify-center bg-background text-sm text-stone-500">正在打开画布...</main>;

    return (
        <main className="h-full overflow-auto bg-background text-stone-950 dark:text-stone-100">
            <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-10">
                <header className="flex flex-wrap items-end justify-between gap-4 border-b border-stone-200 pb-6 dark:border-stone-800">
                    <div>
                        <p className="text-xs text-stone-500">画布库</p>
                        <h1 className="mt-3 text-3xl font-semibold">绘世画布</h1>
                    </div>
                    <div className="flex items-center gap-2">
                        {selectedIds.length ? (
                            <>
                                <Button
                                    disabled={!hydrated}
                                    icon={<Download className="size-4" />}
                                    onClick={() =>
                                        void exportCanvasProjects(
                                            projects.filter((project) => selectedIds.includes(project.id)),
                                            `无限画布-${selectedIds.length}个项目`,
                                        )
                                    }
                                >
                                    导出选中
                                </Button>
                                <Button disabled={!hydrated} onClick={() => setDeleteIds(selectedIds)}>
                                    删除选中
                                </Button>
                            </>
                        ) : null}
                        {projects.length ? (
                            <Button disabled={!hydrated} onClick={() => setDeleteIds(projects.map((project) => project.id))}>
                                删除全部
                            </Button>
                        ) : null}
                        <Button disabled={!hydrated} icon={<FileUp className="size-4" />} onClick={() => inputRef.current?.click()}>
                            导入画布
                        </Button>
                        <Button disabled={!hydrated} type="primary" icon={<Plus className="size-4" />} onClick={createProjectAndStay}>
                            新建画布
                        </Button>
                    </div>
                </header>

                {!hydrated ? (
                    <section className="flex min-h-[360px] items-center justify-center border-y border-stone-200 text-sm text-stone-500 dark:border-stone-800">正在加载画布...</section>
                ) : projects.length ? (
                    <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                        {projects.map((project) => (
                            <CanvasProjectCard key={project.id} project={project} />
                        ))}
                    </div>
                ) : (
                    <section className="flex min-h-[360px] flex-col items-center justify-center border-y border-stone-200 text-center dark:border-stone-800">
                        <h2 className="text-xl font-medium">还没有画布</h2>
                        <p className="mt-3 max-w-md text-sm leading-6 text-stone-500">新建后即可保存节点、连线和画布外观。项目保存在此浏览器，可通过导出功能备份。</p>
                        <Button type="primary" className="mt-6" icon={<Plus className="size-4" />} onClick={createProjectAndStay}>
                            新建画布
                        </Button>
                    </section>
                )}
            </div>

            <input ref={inputRef} type="file" accept="application/zip,.zip" className="hidden" onChange={(event) => void importCanvas(event.target.files?.[0])} />
            <CanvasDeleteProjectsDialog />
        </main>
    );
}
