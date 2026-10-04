"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Settings2 } from "lucide-react";

import { UserStatusActions } from "@/components/layout/user-status-actions";
import { SettingsTabsContent } from "@/components/settings/settings-tabs-content";

export default function SettingsPage() {
    return (
        <Suspense fallback={<SettingsPageShell />}>
            <SettingsPageContent />
        </Suspense>
    );
}

function SettingsPageContent() {
    const searchParams = useSearchParams();
    const defaultTab = searchParams.get("tab") || "channels";
    const [activeTab, setActiveTab] = useState(defaultTab);

    // 监听URL变化
    useEffect(() => {
        const tab = searchParams.get("tab");
        if (tab) setActiveTab(tab);
    }, [searchParams]);

    return (
        <main className="flex h-full min-h-0 flex-col">
            <header className="flex h-16 shrink-0 items-center justify-between border-b px-6">
                <div className="flex items-center gap-3">
                    <Settings2 className="size-5" />
                    <h1 className="text-lg font-semibold">设置</h1>
                </div>
                <UserStatusActions />
            </header>

            <div className="flex min-h-0 flex-1">
                <SettingsTabsContent activeTab={activeTab} onTabChange={setActiveTab} />
            </div>
        </main>
    );
}

function SettingsPageShell() {
    return (
        <main className="flex h-full min-h-0 flex-col">
            <header className="flex h-16 shrink-0 items-center justify-between border-b px-6">
                <div className="flex items-center gap-3">
                    <Settings2 className="size-5" />
                    <h1 className="text-lg font-semibold">设置</h1>
                </div>
                <UserStatusActions />
            </header>
            <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-stone-500">正在加载设置...</div>
        </main>
    );
}
