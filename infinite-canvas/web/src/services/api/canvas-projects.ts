import type { CanvasProject } from "@/app/(user)/canvas/stores/use-canvas-store";

export type RemoteCanvasProject = {
    id: string;
    title: string;
    schemaVersion: number;
    rev: number;
    payload: Pick<CanvasProject, "nodes" | "connections" | "chatSessions" | "activeChatId" | "backgroundMode" | "showImageInfo" | "viewport">;
    createdAt: string;
    updatedAt: string;
};

export class CanvasProjectRevisionConflict extends Error {
    project?: RemoteCanvasProject;

    constructor(project?: RemoteCanvasProject) {
        super("revision_conflict");
        this.name = "CanvasProjectRevisionConflict";
        this.project = project;
    }
}

export function buildCanvasProjectPayload(project: CanvasProject, baseRev = project.remoteRev || 0) {
    return {
        project: {
            id: project.id,
            title: project.title,
            schemaVersion: 1,
            baseRev,
            createdAt: project.createdAt,
            updatedAt: project.updatedAt,
            payload: {
                nodes: project.nodes,
                connections: project.connections,
                chatSessions: project.chatSessions,
                activeChatId: project.activeChatId,
                backgroundMode: project.backgroundMode,
                showImageInfo: project.showImageInfo,
                viewport: project.viewport,
            },
        },
    };
}

function projectUrl(projectsUrl: string, projectId: string) {
    return `${projectsUrl.replace(/\/+$/, "")}/${encodeURIComponent(projectId)}`;
}

async function readProjectResponse(response: Response) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 409) throw new CanvasProjectRevisionConflict(payload.project as RemoteCanvasProject | undefined);
    if (!response.ok || payload.ok === false) throw new Error(String(payload.error || "canvas_project_request_failed"));
    return payload.project as RemoteCanvasProject;
}

export async function listCanvasProjects(projectsUrl: string, token: string) {
    const response = await fetch(projectsUrl, {
        method: "GET",
        headers: { "X-Canvas-Session": token },
        cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) throw new Error(String(payload.error || "canvas_projects_list_failed"));
    return (payload.projects || []) as RemoteCanvasProject[];
}

export async function saveCanvasProject(projectsUrl: string, token: string, project: CanvasProject) {
    const existing = Number(project.remoteRev || 0) > 0;
    const response = await fetch(existing ? projectUrl(projectsUrl, project.id) : projectsUrl, {
        method: existing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", "X-Canvas-Session": token },
        body: JSON.stringify(buildCanvasProjectPayload(project, project.remoteRev || 0)),
        cache: "no-store",
    });
    return readProjectResponse(response);
}

export async function deleteCanvasProject(projectsUrl: string, token: string, projectId: string) {
    const response = await fetch(projectUrl(projectsUrl, projectId), {
        method: "DELETE",
        headers: { "X-Canvas-Session": token },
        cache: "no-store",
    });
    if (!response.ok) throw new Error("canvas_project_delete_failed");
}

export function remoteCanvasProjectToLocal(project: RemoteCanvasProject): CanvasProject {
    return {
        id: project.id,
        title: project.title,
        createdAt: project.createdAt,
        updatedAt: project.updatedAt,
        nodes: project.payload.nodes || [],
        connections: project.payload.connections || [],
        chatSessions: project.payload.chatSessions || [],
        activeChatId: project.payload.activeChatId || null,
        backgroundMode: project.payload.backgroundMode || "lines",
        showImageInfo: project.payload.showImageInfo || false,
        viewport: project.payload.viewport || { x: 0, y: 0, k: 1 },
        remoteRev: project.rev,
        syncStatus: "saved",
    };
}

export function mergeCanvasProjects(localProjects: CanvasProject[], remoteProjects: RemoteCanvasProject[]) {
    const merged = new Map(localProjects.map((project) => [project.id, project]));
    for (const remote of remoteProjects) {
        const local = merged.get(remote.id);
        if (!local) {
            merged.set(remote.id, remoteCanvasProjectToLocal(remote));
            continue;
        }
        const localIsNewer = Date.parse(local.updatedAt || "") > Date.parse(remote.updatedAt || "");
        if (localIsNewer) {
            merged.set(remote.id, { ...local, remoteRev: remote.rev });
        } else if (!local.remoteRev || local.remoteRev < remote.rev) {
            merged.set(remote.id, remoteCanvasProjectToLocal(remote));
        }
    }
    return Array.from(merged.values()).sort((left, right) => Date.parse(right.updatedAt || "") - Date.parse(left.updatedAt || ""));
}

export function shouldSaveCanvasProject(project: CanvasProject, remote?: RemoteCanvasProject) {
    if (project.syncStatus === "saving" || project.syncStatus === "conflict") return false;
    if (!remote) return true;
    if (!project.remoteRev || project.remoteRev < remote.rev) return Date.parse(project.updatedAt || "") > Date.parse(remote.updatedAt || "");
    return Date.parse(project.updatedAt || "") > Date.parse(remote.updatedAt || "");
}
