export type HostCanvasLibraryAsset = {
    id: number;
    title: string;
    image_path: string;
    image_url: string;
    media_url?: string;
    source?: string;
    media_type?: string;
    mime_type?: string;
    created_at: string;
    width: number;
    height: number;
    duration_ms?: number;
};

export type HostCanvasLibraryAssetDetail = HostCanvasLibraryAsset & {
    data_url?: string;
};

export type HostLibraryPickerAsset = {
    id: string;
    kind: "image" | "video" | "audio";
    title: string;
    coverUrl: string;
    tags: string[];
    source?: string;
    note?: string;
    createdAt: string;
    updatedAt: string;
    hostRecordId: number;
    imagePath: string;
    imageUrl: string;
    mediaUrl: string;
    mediaType: string;
    mimeType: string;
    width: number;
    height: number;
    durationMs?: number;
};

export type HostAssetInsertPayload =
    | { kind: "image"; dataUrl: string; title: string }
    | { kind: "video"; url: string; title: string; width?: number; height?: number; mimeType?: string; durationMs?: number }
    | { kind: "audio"; url: string; title: string; mimeType?: string; durationMs?: number };

export function hostAssetToPickerAsset(asset: HostCanvasLibraryAsset): HostLibraryPickerAsset {
    const createdAt = asset.created_at || new Date().toISOString();
    const mediaType = String(asset.media_type || asset.source || "").trim().toLowerCase();
    const mimeType = String(asset.mime_type || "").trim().toLowerCase();
    const kind = mediaKind(mediaType, mimeType, asset.media_url || asset.image_path);
    const mediaUrl = asset.media_url || asset.image_url || asset.image_path;
    return {
        id: `host-${asset.id}`,
        kind,
        title: asset.title || "画布素材",
        coverUrl: kind === "image" ? asset.image_url || asset.image_path : "",
        tags: ["资产库"],
        source: asset.source || "HostAssetLibrary",
        note: "来自主站资产库",
        createdAt,
        updatedAt: createdAt,
        hostRecordId: asset.id,
        imagePath: asset.image_path,
        imageUrl: asset.image_url || asset.image_path,
        mediaUrl,
        mediaType: mediaType || kind,
        mimeType,
        width: asset.width || 0,
        height: asset.height || 0,
        durationMs: asset.duration_ms || 0,
    };
}

export function hostAssetToInsertPayload(asset: HostLibraryPickerAsset, detail: HostCanvasLibraryAssetDetail): HostAssetInsertPayload {
    if (asset.kind === "image") {
        const dataUrl = String(detail.data_url || "");
        if (!dataUrl) throw new Error("素材加载失败");
        return { kind: "image", dataUrl, title: detail.title || asset.title };
    }
    const url = detail.media_url || detail.image_url || detail.image_path || asset.mediaUrl;
    if (!url) throw new Error("素材加载失败");
    if (asset.kind === "video") {
        const durationMs = detail.duration_ms || asset.durationMs || undefined;
        return { kind: "video", url, title: detail.title || asset.title, width: detail.width || asset.width, height: detail.height || asset.height, mimeType: detail.mime_type || asset.mimeType || "video/mp4", ...(durationMs ? { durationMs } : {}) };
    }
    const durationMs = detail.duration_ms || asset.durationMs || undefined;
    return { kind: "audio", url, title: detail.title || asset.title, mimeType: detail.mime_type || asset.mimeType || "audio/mpeg", ...(durationMs ? { durationMs } : {}) };
}

function mediaKind(mediaType: string, mimeType: string, path: string): "image" | "video" | "audio" {
    if (mediaType === "speech" || mediaType === "music" || mediaType === "audio" || mimeType.startsWith("audio/") || /\.(mp3|wav|ogg|opus|m4a|aac|flac)(?:$|\?)/i.test(path)) return "audio";
    if (mediaType === "video" || mimeType.startsWith("video/") || /\.(mp4|webm|mov|m4v)(?:$|\?)/i.test(path)) return "video";
    return "image";
}
