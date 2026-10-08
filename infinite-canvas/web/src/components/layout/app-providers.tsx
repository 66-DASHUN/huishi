"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";

import { ClientRootInit } from "@/components/layout/client-root-init";
import { getAntThemeConfig } from "@/lib/app-theme";
import { useThemeStore } from "@/stores/use-theme-store";

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 30_000,
            retry: false,
            refetchOnWindowFocus: false,
        },
    },
});

export function AppProviders({ children }: { children: ReactNode }) {
    const preference = useThemeStore((state) => state.preference);
    const resolvedTheme = useThemeStore((state) => state.resolvedTheme);
    const setPreference = useThemeStore((state) => state.setPreference);
    const dark = resolvedTheme === "dark";

    useEffect(() => {
        document.documentElement.classList.toggle("dark", dark);
        document.documentElement.dataset.themePreference = preference;
        document.documentElement.dataset.theme = resolvedTheme;
        document.documentElement.style.colorScheme = resolvedTheme;
    }, [dark, preference, resolvedTheme]);

    useEffect(() => {
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        const syncResolvedTheme = () => setPreference(preference);
        syncResolvedTheme();
        media.addEventListener("change", syncResolvedTheme);
        return () => media.removeEventListener("change", syncResolvedTheme);
    }, [preference, setPreference]);

    // ProConfigProvider 已移除：它的唯一作用是给 pro-components 自己的组件
    // 传 dark。本项目一个 pro 组件都没用，却因此把整个 pro-components 拖进
    // 首屏（9MB 包，连带 lodash-es / rc-field-form / dnd-kit / emotion 等）。
    // 暗色主题由下面 ConfigProvider 的 getAntThemeConfig 完整负责
    // （darkAlgorithm + 每组件 dark token），不依赖 pro 的上下文。
    return (
        <ConfigProvider locale={zhCN} theme={getAntThemeConfig(dark)}>
            <App>
                <QueryClientProvider client={queryClient}>
                    <ClientRootInit>{children}</ClientRootInit>
                </QueryClientProvider>
            </App>
        </ConfigProvider>
    );
}
