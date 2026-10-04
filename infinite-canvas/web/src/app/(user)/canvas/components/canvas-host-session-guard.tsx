"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { CanvasStatusScreen } from "./canvas-status-screen";
import { alignHostImageModel, alignHostVideoModel, isHostCanvasMode, parseHostThemeMessage, readHostCanvasBootstrap, verifyHostCanvasSession } from "../lib/host-canvas-session";
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";
import { useCanvasProjectCloudSync } from "../hooks/use-canvas-project-cloud-sync";
import { useThemeStore } from "@/stores/use-theme-store";
import { useConfigStore } from "@/stores/use-config-store";

export function CanvasHostSessionGuard({ children }: { children: React.ReactNode }) {
    const searchParams = useSearchParams();
    const requiresHostSession = useCanvasHostSessionStore((state) => state.requiresHostSession);
    const loading = useCanvasHostSessionStore((state) => state.loading);
    const authenticated = useCanvasHostSessionStore((state) => state.authenticated);
    const setLoading = useCanvasHostSessionStore((state) => state.setLoading);
    const setSession = useCanvasHostSessionStore((state) => state.setSession);
    const setStandalone = useCanvasHostSessionStore((state) => state.setStandalone);
    const hostOrigin = useCanvasHostSessionStore((state) => state.hostOrigin);
    const clearSession = useCanvasHostSessionStore((state) => state.clearSession);
    const applyHostTheme = useThemeStore((state) => state.applyHostTheme);
    const [retryNonce, setRetryNonce] = useState(0);
    const [failureMessage, setFailureMessage] = useState("");
    useCanvasProjectCloudSync();

    useEffect(() => {
        if (loading || (requiresHostSession && !authenticated)) return;
        const targetOrigin = hostOrigin || "*";
        window.parent?.postMessage({ type: "huishi-canvas-ready" }, { targetOrigin });
        const handlePing = (event: MessageEvent) => {
            if (event.source !== window.parent || (hostOrigin && event.origin !== hostOrigin)) return;
            if ((event.data || {}).type !== "huishi-canvas-ping") return;
            event.source?.postMessage({ type: "huishi-canvas-ready" }, { targetOrigin });
        };
        const handleHostTheme = (event: MessageEvent) => {
            if (event.source !== window.parent || !hostOrigin || event.origin !== hostOrigin) return;
            const message = parseHostThemeMessage(event.data);
            if (message) applyHostTheme(message.preference, message.resolvedTheme);
        };
        window.addEventListener("message", handlePing);
        window.addEventListener("message", handleHostTheme);
        return () => {
            window.removeEventListener("message", handlePing);
            window.removeEventListener("message", handleHostTheme);
        };
    }, [applyHostTheme, authenticated, hostOrigin, loading, requiresHostSession]);

    useEffect(() => {
        let active = true;
        const bootstrap = readHostCanvasBootstrap(searchParams);
        if (!bootstrap) {
            if (authenticated) return;
            if (!isHostCanvasMode(searchParams)) {
                setStandalone();
                return;
            }
            setFailureMessage("缺少有效的主站会话，请从绘世重新进入画布。");
            clearSession();
            return;
        }

        setFailureMessage("");
        setLoading(true);
        void verifyHostCanvasSession(bootstrap)
            .then((payload) => {
                if (!active) return;
                if (!payload.authenticated || !payload.user) {
                    setFailureMessage("主站会话已失效，请重新验证或从绘世再次进入。");
                    clearSession();
                    return;
                }
                const imageModels = payload.image_models || [];
                const videoModels = payload.video_models || [];
                const speechModels = payload.speech_models || [];
                const musicModels = payload.music_models || [];
                const configStore = useConfigStore.getState();
                configStore.updateConfig("hostVideoModels", videoModels);
                const alignedImageModel = alignHostImageModel(configStore.config.imageModel, imageModels);
                const alignedVideoModel = alignHostVideoModel(configStore.config.videoModel, videoModels);
                const alignedSpeechModel = alignHostVideoModel(configStore.config.speechModel, speechModels);
                const alignedMusicModel = alignHostVideoModel(configStore.config.musicModel, musicModels);
                if (configStore.config.imageModel !== alignedImageModel) {
                    configStore.updateConfig("imageModel", alignedImageModel);
                }
                if (configStore.config.videoModel !== alignedVideoModel) {
                    configStore.updateConfig("videoModel", alignedVideoModel);
                }
                if (configStore.config.speechModel !== alignedSpeechModel) {
                    configStore.updateConfig("speechModel", alignedSpeechModel);
                }
                if (configStore.config.musicModel !== alignedMusicModel) {
                    configStore.updateConfig("musicModel", alignedMusicModel);
                }
                setSession({
                    userId: payload.user.id,
                    username: payload.user.username,
                    role: payload.user.role,
                    billingIdentity: payload.billing_identity || `user:${payload.user.id}`,
                    expiresAt: payload.expires_at || null,
                    token: bootstrap.token,
                    verifyUrl: bootstrap.verifyUrl,
                    assetsLibraryUrl: bootstrap.assetsLibraryUrl,
                    generateUrl: bootstrap.generateUrl,
                    videoTasksUrl: bootstrap.videoTasksUrl,
                    chatUrl: bootstrap.chatUrl,
                    projectsUrl: bootstrap.projectsUrl,
                    hostOrigin: bootstrap.hostOrigin,
                    imageModels,
                    videoModels,
                    speechModels,
                    musicModels,
                });
            })
            .catch(() => {
                if (!active) return;
                setFailureMessage(navigator.onLine ? "暂时无法验证主站会话，请稍后重试。" : "网络连接已断开，请联网后重试。");
                clearSession();
            });

        return () => {
            active = false;
        };
    }, [authenticated, searchParams, clearSession, retryNonce, setLoading, setSession, setStandalone]);

    if (!requiresHostSession) return <>{children}</>;

    if (loading) {
        return <CanvasStatusScreen status="session" loading onAction={() => setRetryNonce((value) => value + 1)} />;
    }

    if (!authenticated) {
        return <CanvasStatusScreen status="session" title="画布会话未授权" description={failureMessage || "画布会话未授权，请从主站重新进入。"} actionLabel="重新验证" onAction={() => setRetryNonce((value) => value + 1)} />;
    }

    return <>{children}</>;
}
