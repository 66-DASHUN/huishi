"use client";

import { useEffect, useMemo, useState } from "react";
import { Empty, Input, Modal, Pagination, Spin, Tag } from "antd";
import { FolderSync, Search } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAssetStore, type Asset } from "@/stores/use-asset-store";
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";
import { hostAssetToInsertPayload, hostAssetToPickerAsset, type HostCanvasLibraryAsset, type HostCanvasLibraryAssetDetail, type HostLibraryPickerAsset } from "./canvas-host-asset";

export type InsertAssetPayload =
    | { kind: "text"; content: string; title: string }
    | { kind: "image"; dataUrl: string; title: string; storageKey?: string }
    | { kind: "video"; url: string; title: string; storageKey?: string; width?: number; height?: number }
    | { kind: "audio"; url: string; title: string; storageKey?: string; mimeType?: string; durationMs?: number };

type Props = {
    open: boolean;
    defaultTab?: string;
    onInsert: (payload: InsertAssetPayload) => void;
    onClose: () => void;
};

type PickerAsset = Asset | HostLibraryPickerAsset;

const PAGE_SIZE = 8;

const kindOptions = [
    { label: "全部", value: "all" },
    { label: "文本", value: "text" },
    { label: "图片", value: "image" },
    { label: "视频", value: "video" },
    { label: "音频", value: "audio" },
];

export function AssetPickerModal({ open, onInsert, onClose }: Props) {
    return (
        <Modal title="选择素材" open={open} onCancel={onClose} footer={null} width={860} destroyOnHidden styles={{ body: { padding: "0 24px 24px", minHeight: 480 } }}>
            <MyAssetsTab onInsert={onInsert} />
        </Modal>
    );
}

function PickerCard({ title, kind, cover, onClick }: { title: string; kind: string; cover: string; onClick: () => void }) {
    return (
        <button
            type="button"
            className="group relative cursor-pointer overflow-hidden rounded-lg border border-stone-200 bg-white text-left transition hover:border-stone-400 hover:shadow-md dark:border-stone-700 dark:bg-stone-900 dark:hover:border-stone-500"
            onClick={onClick}
        >
            {cover ? (
                <img src={cover} alt={title} loading="lazy" decoding="async" className="aspect-[4/3] w-full object-cover" />
            ) : (
                <div className="flex aspect-[4/3] items-center justify-center bg-stone-100 p-3 text-center text-xs leading-5 text-stone-500 dark:bg-stone-800 dark:text-stone-400">{title}</div>
            )}
            <div className="p-2.5">
                <div className="flex items-center justify-between gap-2">
                    <span className="line-clamp-1 text-xs font-medium text-stone-800 dark:text-stone-200">{title}</span>
                    <Tag className="m-0 shrink-0 text-[10px]">{kind === "image" ? "图片" : kind === "video" ? "视频" : kind === "audio" ? "音频" : "文本"}</Tag>
                </div>
            </div>
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-stone-950/0 text-sm font-medium text-white opacity-0 transition group-hover:bg-stone-950/55 group-hover:opacity-100">插入</div>
        </button>
    );
}

function MyAssetsTab({ onInsert }: { onInsert: (payload: InsertAssetPayload) => void }) {
    const assets = useAssetStore((state) => state.assets);
    const hostToken = useCanvasHostSessionStore((state) => state.token);
    const assetsLibraryUrl = useCanvasHostSessionStore((state) => state.assetsLibraryUrl);
    const [keyword, setKeyword] = useState("");
    const [kindFilter, setKindFilter] = useState("all");
    const [page, setPage] = useState(1);
    const [libraryAssets, setLibraryAssets] = useState<HostLibraryPickerAsset[]>([]);
    const [libraryLoading, setLibraryLoading] = useState(false);
    const [libraryError, setLibraryError] = useState("");

    const filtered = useMemo(() => {
        const query = keyword.trim().toLowerCase();
        return [...assets, ...libraryAssets]
            .filter((asset) => asset.kind === "text" || asset.kind === "image" || asset.kind === "video" || asset.kind === "audio")
            .filter((asset) => kindFilter === "all" || asset.kind === kindFilter)
            .filter((asset) => !query || [asset.title, ...(asset.tags || [])].join(" ").toLowerCase().includes(query));
    }, [assets, keyword, kindFilter, libraryAssets]);

    const visible = useMemo(() => filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), [filtered, page]);

    useEffect(() => {
        const maxPage = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
        setPage((value) => Math.min(value, maxPage));
    }, [filtered.length]);

    useEffect(() => {
        let active = true;
        if (!assetsLibraryUrl || !hostToken) {
            setLibraryAssets([]);
            setLibraryLoading(false);
            setLibraryError("");
            return;
        }

        setLibraryLoading(true);
        setLibraryError("");
        void fetch(assetsLibraryUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Canvas-Session": hostToken },
            body: JSON.stringify({}),
            cache: "no-store",
        })
            .then(async (response) => {
                const payload = (await response.json()) as { ok?: boolean; error?: string; assets?: HostCanvasLibraryAsset[] };
                if (!response.ok || !payload.ok) throw new Error(payload.error || "资产库加载失败");
                if (!active) return;
                setLibraryAssets((payload.assets || []).map(hostAssetToPickerAsset));
            })
            .catch((error: unknown) => {
                if (!active) return;
                setLibraryAssets([]);
                setLibraryError(error instanceof Error ? error.message : "资产库加载失败");
            })
            .finally(() => {
                if (active) setLibraryLoading(false);
            });

        return () => {
            active = false;
        };
    }, [assetsLibraryUrl, hostToken]);

    const handleInsert = async (asset: PickerAsset) => {
        if (isHostLibraryPickerAsset(asset)) {
            if (!assetsLibraryUrl || !hostToken) return;
            try {
                const response = await fetch(`${assetsLibraryUrl}/${asset.hostRecordId}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-Canvas-Session": hostToken },
                    body: JSON.stringify({}),
                    cache: "no-store",
                });
                const payload = (await response.json()) as { ok?: boolean; error?: string; asset?: HostCanvasLibraryAssetDetail };
                if (!response.ok || !payload.ok || !payload.asset) throw new Error(payload.error || "素材加载失败");
                onInsert(hostAssetToInsertPayload(asset, payload.asset));
            } catch (error) {
                setLibraryError(error instanceof Error ? error.message : "素材加载失败");
            }
            return;
        }

        if (asset.kind === "text") {
            onInsert({ kind: "text", content: asset.data.content, title: asset.title });
            return;
        }

        if (asset.kind === "video") {
            onInsert({ kind: "video", url: asset.data.url, storageKey: asset.data.storageKey, title: asset.title, width: asset.data.width, height: asset.data.height });
            return;
        }

        onInsert({ kind: "image", dataUrl: asset.data.dataUrl, storageKey: asset.data.storageKey, title: asset.title });
    };

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
                <Input
                    className="w-56"
                    size="small"
                    prefix={<Search className="size-3.5 text-stone-400" />}
                    placeholder="搜索素材"
                    value={keyword}
                    allowClear
                    onChange={(event) => {
                        setPage(1);
                        setKeyword(event.target.value);
                    }}
                />
                <div className="flex gap-1.5">
                    {kindOptions.map((option) => (
                        <Tag.CheckableTag
                            key={option.value}
                            checked={kindFilter === option.value}
                            className={cn("prompt-filter-tag", kindFilter === option.value && "is-active")}
                            onChange={() => {
                                setPage(1);
                                setKindFilter(option.value);
                            }}
                        >
                            {option.label}
                        </Tag.CheckableTag>
                    ))}
                </div>
                {assetsLibraryUrl ? (
                    <span className="inline-flex items-center gap-1 text-xs text-stone-500">
                        <FolderSync className="size-3.5" />
                        资产库素材已并入我的素材
                    </span>
                ) : null}
            </div>

            {libraryLoading ? (
                <div className="flex items-center gap-2 text-xs text-stone-500">
                    <Spin size="small" />
                    正在同步资产库素材
                </div>
            ) : null}

            {libraryError ? <div className="text-xs text-rose-500">{libraryError}</div> : null}

            {visible.length ? (
                <div className="grid grid-cols-4 gap-3">
                    {visible.map((asset) => (
                        <PickerCard
                            key={asset.id}
                            title={asset.title}
                            kind={asset.kind}
                            cover={pickerAssetCover(asset)}
                            onClick={() => {
                                void handleInsert(asset);
                            }}
                        />
                    ))}
                </div>
            ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有素材" className="py-12" />
            )}

            {filtered.length > PAGE_SIZE ? (
                <div className="flex justify-center">
                    <Pagination size="small" current={page} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} showSizeChanger={false} />
                </div>
            ) : null}
        </div>
    );
}

function isHostLibraryPickerAsset(asset: PickerAsset): asset is HostLibraryPickerAsset {
    return "hostRecordId" in asset;
}

function pickerAssetCover(asset: PickerAsset) {
    if (isHostLibraryPickerAsset(asset)) return asset.coverUrl;
    return asset.coverUrl || (asset.kind === "image" ? asset.data.dataUrl : "");
}
