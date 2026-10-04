"use client";

/**
 * 设置页Tab内容组件
 * 复用AppConfigModal的逻辑，但去掉Modal包装
 */

import { App, Button, Form, Input, Progress, Select, Tabs } from "antd";
import { CircleAlert, Cloud, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";

import { ModelPicker } from "@/components/model-picker";
import { fetchChannelModels } from "@/services/api/image";
import { syncAppDataToWebdav, type AppSyncDomainKey, type AppSyncProgressEvent } from "@/services/app-sync";
import { testWebdavConnection } from "@/services/webdav-sync";
import { createModelChannel, defaultBaseUrlForApiFormat, modelOptionLabel, uniqueModels, useConfigStore, withChannels, type ApiCallFormat, type ModelChannel } from "@/stores/use-config-store";

const apiFormatOptions: Array<{ label: string; value: ApiCallFormat }> = [
    { label: "OpenAI", value: "openai" },
    { label: "Gemini", value: "gemini" },
    { label: "Grok", value: "grok" },
    { label: "Seedance", value: "seedance" },
    { label: "MiniMax", value: "minimax" },
];

const apiFormatLabel = (format: ApiCallFormat) => apiFormatOptions.find((opt) => opt.value === format)?.label || format;

export function SettingsTabsContent({ activeTab, onTabChange }: { activeTab: string; onTabChange: (key: string) => void }) {
    const { message } = App.useApp();
    const [loadingChannelId, setLoadingChannelId] = useState("");
    const [testingWebdav, setTestingWebdav] = useState(false);
    const [syncingWebdav, setSyncingWebdav] = useState(false);

    const config = useConfigStore((state) => state.config);
    const webdav = useConfigStore((state) => state.webdav);
    const saveConfig = useConfigStore((state) => state.saveConfig);
    const updateWebdav = useConfigStore((state) => state.updateWebdav);

    const updateChannels = (channels: ModelChannel[]) => {
        const nextConfig = withChannels(config, channels);
        saveConfig(nextConfig);
    };

    const updateChannel = (id: string, patch: Partial<ModelChannel>) => {
        updateChannels(config.channels.map((channel) => (channel.id === id ? { ...channel, ...patch, models: patch.models ? uniqueModels(patch.models) : channel.models } : channel)));
    };

    const addChannel = () => {
        updateChannels([...config.channels, createModelChannel({ name: `渠道 ${config.channels.length + 1}` })]);
    };

    const deleteChannel = (id: string) => {
        if (config.channels.length <= 1) {
            message.warning("至少保留一个渠道");
            return;
        }
        updateChannels(config.channels.filter((ch) => ch.id !== id));
        message.success("已删除渠道");
    };

    const refreshChannelModels = async (channel: ModelChannel) => {
        setLoadingChannelId(channel.id);
        try {
            const models = await fetchChannelModels(channel);
            updateChannel(channel.id, { models });
            message.success(`成功拉取 ${models.length} 个模型`);
        } catch (error: any) {
            message.error(`拉取失败: ${error.message}`);
        } finally {
            setLoadingChannelId("");
        }
    };

    const refreshAllModels = async () => {
        setLoadingChannelId("all");
        const results = await Promise.allSettled(
            config.channels.map(async (channel) => {
                const models = await fetchChannelModels(channel);
                return { channelId: channel.id, models };
            }),
        );

        const succeeded = results.filter((r) => r.status === "fulfilled") as PromiseFulfilledResult<{ channelId: string; models: string[] }>[];
        if (succeeded.length > 0) {
            const updatedChannels = config.channels.map((channel) => {
                const result = succeeded.find((r) => r.value.channelId === channel.id);
                return result ? { ...channel, models: uniqueModels(result.value.models) } : channel;
            });
            updateChannels(updatedChannels);
            message.success(`成功拉取 ${succeeded.length}/${config.channels.length} 个渠道的模型`);
        }

        setLoadingChannelId("");
    };

    const handleTestWebdav = async () => {
        setTestingWebdav(true);
        try {
            await testWebdavConnection(webdav);
            message.success("WebDAV 连接测试成功");
        } catch (error: any) {
            message.error(`连接失败: ${error.message}`);
        } finally {
            setTestingWebdav(false);
        }
    };

    const handleSyncWebdav = async () => {
        setSyncingWebdav(true);
        try {
            await syncAppDataToWebdav(webdav, (event: AppSyncProgressEvent) => {
                // 进度更新逻辑可以在这里添加
            });
            message.success("同步完成");
        } catch (error: any) {
            message.error(`同步失败: ${error.message}`);
        } finally {
            setSyncingWebdav(false);
        }
    };

    return (
        <Tabs
            activeKey={activeTab}
            onChange={onTabChange}
            tabPosition="left"
            className="h-full w-full"
            items={[
                {
                    key: "channels",
                    label: "渠道管理",
                    children: (
                        <div className="space-y-4 p-6">
                            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-stone-200 p-3 dark:border-stone-800">
                                <div className="min-w-0 flex-1">
                                    <div className="flex w-fit max-w-full flex-wrap items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100">
                                        <CircleAlert className="size-3.5 shrink-0" />
                                        <span className="font-semibold">重要：</span>
                                        <span>新增或拉取模型后，需要到"模型管理"Tab 选择可选项才会显示。</span>
                                        <Button type="link" size="small" className="h-auto p-0 text-xs font-semibold text-amber-900 dark:text-amber-100" onClick={() => onTabChange("models")}>
                                            去模型设置
                                        </Button>
                                    </div>
                                </div>
                                <div className="flex shrink-0 gap-2">
                                    <Button icon={<RefreshCw className="size-4" />} loading={Boolean(loadingChannelId)} onClick={() => void refreshAllModels()}>
                                        拉取全部
                                    </Button>
                                    <Button type="primary" icon={<Plus className="size-4" />} onClick={addChannel}>
                                        新增渠道
                                    </Button>
                                </div>
                            </div>

                            <div className="space-y-3">
                                {config.channels.map((channel) => (
                                    <section key={channel.id} className="rounded-lg border border-stone-200 p-3 dark:border-stone-800">
                                        <div className="mb-3 flex items-center justify-between gap-3">
                                            <div className="min-w-0">
                                                <div className="truncate text-sm font-semibold">{channel.name || "未命名渠道"}</div>
                                                <div className="mt-1 text-xs text-stone-500">
                                                    {apiFormatLabel(channel.apiFormat)} · 已保存 {channel.models.length} 个模型
                                                </div>
                                            </div>
                                            <div className="flex shrink-0 gap-2">
                                                <Button size="small" loading={loadingChannelId === channel.id} onClick={() => void refreshChannelModels(channel)}>
                                                    拉取模型
                                                </Button>
                                                <Button size="small" danger icon={<Trash2 className="size-3.5" />} onClick={() => deleteChannel(channel.id)} />
                                            </div>
                                        </div>

                                        <Form layout="vertical" className="space-y-3">
                                            <Form.Item label="渠道名称" className="mb-2">
                                                <Input value={channel.name} onChange={(e) => updateChannel(channel.id, { name: e.target.value })} placeholder="例如：OpenAI 官方" />
                                            </Form.Item>

                                            <Form.Item label="调用格式" className="mb-2">
                                                <Select value={channel.apiFormat} onChange={(value) => updateChannel(channel.id, { apiFormat: value })} options={apiFormatOptions} />
                                            </Form.Item>

                                            <Form.Item label="Base URL" className="mb-2">
                                                <Input value={channel.baseUrl} onChange={(e) => updateChannel(channel.id, { baseUrl: e.target.value })} placeholder={defaultBaseUrlForApiFormat(channel.apiFormat)} />
                                            </Form.Item>

                                            <Form.Item label="API Key" className="mb-2">
                                                <Input.Password value={channel.apiKey} onChange={(e) => updateChannel(channel.id, { apiKey: e.target.value })} placeholder="sk-..." />
                                            </Form.Item>
                                        </Form>
                                    </section>
                                ))}
                            </div>
                        </div>
                    ),
                },
                {
                    key: "models",
                    label: "模型管理",
                    children: (
                        <div className="space-y-6 p-6">
                            <section>
                                <h2 className="mb-4 text-base font-semibold">默认模型</h2>
                                <div className="space-y-3">
                                    <div className="grid grid-cols-[140px_1fr] items-center gap-3">
                                        <span className="text-sm">图像生成</span>
                                        <ModelPicker config={config} value={config.imageModel} onChange={(model) => saveConfig({ ...config, imageModel: model })} capability="image" fullWidth />
                                    </div>
                                    <div className="grid grid-cols-[140px_1fr] items-center gap-3">
                                        <span className="text-sm">视频生成</span>
                                        <ModelPicker config={config} value={config.videoModel} onChange={(model) => saveConfig({ ...config, videoModel: model })} capability="video" fullWidth />
                                    </div>
                                    <div className="grid grid-cols-[140px_1fr] items-center gap-3">
                                        <span className="text-sm">文本生成</span>
                                        <ModelPicker config={config} value={config.textModel} onChange={(model) => saveConfig({ ...config, textModel: model })} capability="text" fullWidth />
                                    </div>
                                    <div className="grid grid-cols-[140px_1fr] items-center gap-3">
                                        <span className="text-sm">音频生成</span>
                                        <ModelPicker config={config} value={config.audioModel} onChange={(model) => saveConfig({ ...config, audioModel: model })} capability="audio" fullWidth />
                                    </div>
                                </div>
                            </section>
                        </div>
                    ),
                },
                {
                    key: "agent",
                    label: "Agent配置",
                    children: (
                        <div className="space-y-6 p-6">
                            <div className="mb-3 rounded-lg bg-blue-50 p-4 text-sm text-blue-900 dark:bg-blue-950/30 dark:text-blue-300">网站 Agent 直接使用当前网页配置的文本模型和 API。</div>
                            <section>
                                <h2 className="mb-4 text-base font-semibold">本地 Codex 连接</h2>
                                <div className="space-y-4">
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">本地 Codex 地址</label>
                                        <Input value={config.codexAgentUrl || ""} onChange={(e) => saveConfig({ ...config, codexAgentUrl: e.target.value })} placeholder="http://localhost:8765" className="w-full max-w-md" />
                                    </div>
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">访问令牌（可选）</label>
                                        <Input.Password value={config.codexAgentToken || ""} onChange={(e) => saveConfig({ ...config, codexAgentToken: e.target.value })} placeholder="可选" className="w-full max-w-md" />
                                    </div>
                                </div>
                            </section>
                        </div>
                    ),
                },
                {
                    key: "webdav",
                    label: "数据同步",
                    children: (
                        <div className="space-y-6 p-6">
                            <section>
                                <h2 className="mb-4 text-base font-semibold">WebDAV 配置</h2>
                                <div className="space-y-4">
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">连接方式</label>
                                        <Select
                                            value={webdav.proxyMode}
                                            onChange={(value) => updateWebdav({ proxyMode: value })}
                                            className="w-full max-w-md"
                                            options={[
                                                { label: "前端直连", value: "direct" },
                                                { label: "Next.js 转发", value: "nextjs" },
                                            ]}
                                        />
                                    </div>
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">WebDAV URL</label>
                                        <Input value={webdav.url} onChange={(e) => updateWebdav({ url: e.target.value })} placeholder="https://dav.example.com" className="w-full max-w-md" />
                                    </div>
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">用户名</label>
                                        <Input value={webdav.username} onChange={(e) => updateWebdav({ username: e.target.value })} className="w-full max-w-md" />
                                    </div>
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">密码</label>
                                        <Input.Password value={webdav.password} onChange={(e) => updateWebdav({ password: e.target.value })} className="w-full max-w-md" />
                                    </div>
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <label className="text-sm">目录</label>
                                        <Input value={webdav.directory} onChange={(e) => updateWebdav({ directory: e.target.value })} placeholder="/infinite-canvas" className="w-full max-w-md" />
                                    </div>
                                    <div className="grid grid-cols-[200px_1fr] items-center gap-4">
                                        <div />
                                        <div className="flex gap-2">
                                            <Button loading={testingWebdav} onClick={handleTestWebdav}>
                                                测试连接
                                            </Button>
                                            <Button type="primary" loading={syncingWebdav} onClick={handleSyncWebdav}>
                                                立即同步
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </div>
                    ),
                },
                {
                    key: "about",
                    label: "关于",
                    children: (
                        <div className="space-y-6 p-6">
                            <section>
                                <h2 className="mb-4 text-base font-semibold">Infinite Canvas</h2>
                                <p className="text-sm text-muted-foreground">无限画布 - AI 创作工作台</p>
                                <p className="mt-2 text-xs text-muted-foreground">Version 0.1.0</p>
                            </section>
                        </div>
                    ),
                },
            ]}
        />
    );
}
