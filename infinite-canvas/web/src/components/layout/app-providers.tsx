"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { ProConfigProvider } from "@ant-design/pro-components";
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

    return (
        <ConfigProvider locale={zhCN} theme={getAntThemeConfig(dark)}>
            <ProConfigProvider dark={dark}>
                <App>
                    <QueryClientProvider client={queryClient}>
                        <ClientRootInit>{children}</ClientRootInit>
                    </QueryClientProvider>
                </App>
            </ProConfigProvider>
        </ConfigProvider>
    );
}
