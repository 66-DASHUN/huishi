"use client";

import type { ResolvedTheme, ThemePreference } from "@/stores/use-theme-store";
import { modelOptionName } from "@/stores/use-config-store";
import type { HostVideoModel } from "@/lib/media-model-capabilities";

export type HostCanvasSessionBootstrap = {
    mode: string;
    token: string;
    verifyUrl: string;
    assetsLibraryUrl: string;
    generateUrl: string;
    videoTasksUrl: string;
    chatUrl: string;
    projectsUrl: string;
    hostOrigin: string;
};

export type HostCanvasSessionPayload = {
    authenticated: boolean;
    user?: {
        id: number;
        username: string;
        role: "user" | "admin";
        points: number;
    };
    billing_identity?: string;
    expires_at?: number;
    image_models?: Array<{ id: string; label: string; resolutions: string[] }>;
    video_models?: HostVideoModel[];
    speech_models?: Array<{ id: string; label: string }>;
    music_models?: Array<{ id: string; label: string }>;
    reason?: string;
};

export type HostThemeMessage = {
    type: "huishi-theme-change";
    preference: ThemePreference;
    resolvedTheme: ResolvedTheme;
};

export function alignHostImageModel(
    currentModel: string,
    imageModels: Array<{ id: string }>,
) {
    const normalizedCurrent = modelOptionName(currentModel);
    if (imageModels.some((model) => model.id === normalizedCurrent)) return normalizedCurrent;
    return imageModels[0]?.id || "";
}

export function alignHostVideoModel(
    currentModel: string,
    videoModels: Array<{ id: string }>,
) {
    const normalizedCurrent = modelOptionName(currentModel);
    if (videoModels.some((model) => model.id === normalizedCurrent)) return normalizedCurrent;
    return videoModels[0]?.id || "";
}

export function parseHostThemeMessage(data: unknown): HostThemeMessage | null {
    if (!data || typeof data !== "object") return null;
    const value = data as Record<string, unknown>;
    if (value.type !== "huishi-theme-change") return null;
    if (!(["system", "light", "dark"] as const).includes(value.preference as ThemePreference)) return null;
    if (!(["light", "dark"] as const).includes(value.resolvedTheme as ResolvedTheme)) return null;
    return value as HostThemeMessage;
}

export function isHostCanvasMode(search: URLSearchParams) {
    return (search.get("host_mode") || "") === "huishi";
}

function normalizedOrigin(value: string) {
    try {
        return new URL(value).origin;
    } catch {
        return "";
    }
}

/**
 * Read the host session token from a canvas URL.
 *
 * The token is a bearer credential, so the host puts it in the URL *fragment*
 * (after "#"): fragments are never sent to the server, which keeps the token
 * out of access logs, and they are also excluded from the Referer header and
 * from the browser-history entry for the embed URL.
 *
 * The query-string lookup is retained so a canvas page already open from
 * before this change keeps working; it can be dropped once no such page can
 * still be live.
 */
export function readHostSessionToken(location?: { hash?: string; search?: string }) {
    const source = location ?? (typeof window !== "undefined" ? window.location : undefined);
    if (!source) return "";
    const fromFragment = new URLSearchParams((source.hash || "").replace(/^#/, "")).get("host_session_token");
    if (fromFragment) return fromFragment;
    return new URLSearchParams(source.search || "").get("host_session_token") || "";
}

export function isTrustedHostFrameOrigin(hostOrigin: string) {
    if (typeof window === "undefined" || window.parent === window || !document.referrer) return false;
    return normalizedOrigin(hostOrigin) === normalizedOrigin(document.referrer);
}

function hasOrigin(value: string, expectedOrigin: string) {
    return normalizedOrigin(value) === normalizedOrigin(expectedOrigin);
}

export function readHostCanvasBootstrap(search: URLSearchParams): HostCanvasSessionBootstrap | null {
    const mode = search.get("host_mode") || "";
    const token = readHostSessionToken() || search.get("host_session_token") || "";
    const verifyUrl = search.get("host_session_verify_url") || "";
    const assetsLibraryUrl = search.get("host_assets_library_url") || "";
    const generateUrl = search.get("host_generate_url") || "";
    const chatUrl = search.get("host_chat_url") || "";
    const projectsUrl = search.get("host_projects_url") || "";
    const hostOrigin = search.get("host_origin") || "";
    const videoTasksUrl = search.get("host_video_tasks_url") || `${hostOrigin}/api/video/tasks`;
    if (mode !== "huishi" || !token || !verifyUrl || !assetsLibraryUrl || !generateUrl || !chatUrl || !projectsUrl || !isTrustedHostFrameOrigin(hostOrigin)) return null;
    if (![verifyUrl, assetsLibraryUrl, generateUrl, videoTasksUrl, chatUrl, projectsUrl].every((url) => hasOrigin(url, hostOrigin))) return null;
    return { mode, token, verifyUrl, assetsLibraryUrl, generateUrl, videoTasksUrl, chatUrl, projectsUrl, hostOrigin };
}

export function hostSettingsHref(hostOrigin: string) {
    if (!isTrustedHostFrameOrigin(hostOrigin)) return "";
    try {
        const url = new URL("/admin/config/settings", hostOrigin);
        url.hash = "settings-image";
        return url.toString();
    } catch {
        return "";
    }
}

export function canvasSettingsHref(hostOrigin: string, requiresHostSession: boolean) {
    return hostSettingsHref(hostOrigin) || (requiresHostSession ? "" : "/settings?tab=channels");
}

export async function verifyHostCanvasSession(bootstrap: HostCanvasSessionBootstrap): Promise<HostCanvasSessionPayload> {
    const response = await fetch(bootstrap.verifyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Canvas-Session": bootstrap.token },
        body: JSON.stringify({}),
        cache: "no-store",
    });
    const payload = (await response.json()) as HostCanvasSessionPayload;
    if (!response.ok) return { ...payload, authenticated: false };
    if (typeof window !== "undefined") {
        const cleanUrl = new URL(window.location.href);
        ["host_session_token", "host_session_verify_url", "host_assets_library_url", "host_generate_url", "host_video_tasks_url", "host_chat_url", "host_projects_url", "host_user_key_url"].forEach((key) => cleanUrl.searchParams.delete(key));
        // Drop the token from the fragment too, so it does not linger in the
        // address bar or the history entry after the session is established.
        const fragment = new URLSearchParams(cleanUrl.hash.replace(/^#/, ""));
        fragment.delete("host_session_token");
        cleanUrl.hash = fragment.toString() ? `#${fragment.toString()}` : "";
        window.history.replaceState({}, document.title, cleanUrl.toString());
    }
    return payload;
}
