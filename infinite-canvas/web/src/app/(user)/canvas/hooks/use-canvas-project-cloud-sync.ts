"use client";

import { useEffect, useRef } from "react";

import { CanvasProjectRevisionConflict, deleteCanvasProject, listCanvasProjects, mergeCanvasProjects, saveCanvasProject, shouldSaveCanvasProject, type RemoteCanvasProject } from "@/services/api/canvas-projects";
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";
import { useCanvasStore, type CanvasProject } from "../stores/use-canvas-store";

function sameProjects(left: CanvasProject[], right: CanvasProject[]) {
    return JSON.stringify(left) === JSON.stringify(right);
}

export function useCanvasProjectCloudSync() {
    const hydrated = useCanvasStore((state) => state.hydrated);
    const projects = useCanvasStore((state) => state.projects);
    const replaceProjects = useCanvasStore((state) => state.replaceProjects);
    const markProjectSynced = useCanvasStore((state) => state.markProjectSynced);
    const markProjectSyncStatus = useCanvasStore((state) => state.markProjectSyncStatus);
    const authenticated = useCanvasHostSessionStore((state) => state.authenticated);
    const token = useCanvasHostSessionStore((state) => state.token);
    const projectsUrl = useCanvasHostSessionStore((state) => state.projectsUrl);
    const syncingRef = useRef(false);
    const pendingRef = useRef(false);
    const knownRemoteIdsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        if (!hydrated || !authenticated || !token || !projectsUrl) return;
        if (!navigator.onLine) {
            projects.forEach((project) => markProjectSyncStatus(project.id, "offline"));
            return;
        }

        let cancelled = false;
        const timer = window.setTimeout(() => {
            const run = async () => {
                if (syncingRef.current) {
                    pendingRef.current = true;
                    return;
                }
                syncingRef.current = true;
                pendingRef.current = false;
                try {
                    const snapshot = useCanvasStore.getState().projects;
                    const remoteProjects = await listCanvasProjects(projectsUrl, token);
                    const remoteById = new Map(remoteProjects.map((project) => [project.id, project]));
                    const currentIds = new Set(snapshot.map((project) => project.id));
                    const removedIds = Array.from(knownRemoteIdsRef.current).filter((id) => !currentIds.has(id));
                    const merged = mergeCanvasProjects(snapshot, remoteProjects);
                    if (!sameProjects(snapshot, merged)) replaceProjects(merged);

                    await Promise.all(removedIds.map((id) => deleteCanvasProject(projectsUrl, token, id).catch(() => undefined)));

                    for (const project of merged) {
                        if (cancelled || !shouldSaveCanvasProject(project, remoteById.get(project.id))) continue;
                        markProjectSyncStatus(project.id, "saving");
                        try {
                            const saved = await saveCanvasProject(projectsUrl, token, project);
                            markProjectSynced(project.id, saved.rev);
                            remoteById.set(saved.id, saved);
                        } catch (error) {
                            if (error instanceof CanvasProjectRevisionConflict) markProjectSyncStatus(project.id, "conflict");
                            else markProjectSyncStatus(project.id, navigator.onLine ? "offline" : "offline");
                        }
                    }
                    const latest = useCanvasStore.getState().projects;
                    knownRemoteIdsRef.current = new Set(latest.filter((project) => Number(project.remoteRev || 0) > 0).map((project) => project.id));
                } catch {
                    useCanvasStore.getState().projects.forEach((project) => markProjectSyncStatus(project.id, "offline"));
                } finally {
                    syncingRef.current = false;
                    if (!cancelled && pendingRef.current) void run();
                }
            };
            void run();
        }, 700);

        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, [authenticated, hydrated, markProjectSynced, markProjectSyncStatus, projects, projectsUrl, replaceProjects, token]);
}
