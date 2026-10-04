import { NODE_DEFAULT_SIZE, getNodeSpec } from "../constants";
import { CanvasNodeType, type CanvasNodeData, type Position } from "../types";
import { fitNodeSize } from "./canvas-node-size";

type BaseCanvasAsset = { id: string; title: string };

export type CanvasAssetInsertion =
    | (BaseCanvasAsset & { kind: "text"; content: string })
    | (BaseCanvasAsset & { kind: "image"; url: string; storageKey?: string; width: number; height: number; bytes?: number; mimeType?: string; prompt?: string })
    | (BaseCanvasAsset & { kind: "video"; url: string; storageKey?: string; width?: number; height?: number; bytes?: number; mimeType?: string; durationMs?: number })
    | (BaseCanvasAsset & { kind: "audio"; url: string; storageKey?: string; bytes?: number; mimeType?: string; durationMs?: number });

export function assetToCanvasNode(asset: CanvasAssetInsertion, center: Position): CanvasNodeData {
    if (asset.kind === "text") {
        const spec = getNodeSpec(CanvasNodeType.Text);
        return centeredNode(asset.id, CanvasNodeType.Text, asset.title, center, spec.width, spec.height, {
            ...spec.metadata,
            content: asset.content,
            status: "success",
        });
    }

    if (asset.kind === "image") {
        const size = fitNodeSize(asset.width, asset.height);
        return centeredNode(asset.id, CanvasNodeType.Image, asset.title, center, size.width, size.height, {
            content: asset.url,
            storageKey: asset.storageKey,
            status: "success",
            naturalWidth: asset.width,
            naturalHeight: asset.height,
            bytes: asset.bytes,
            mimeType: asset.mimeType,
            prompt: asset.prompt,
        });
    }

    if (asset.kind === "video") {
        const spec = NODE_DEFAULT_SIZE[CanvasNodeType.Video];
        const size = fitNodeSize(asset.width || spec.width, asset.height || spec.height, spec.width, 420);
        return centeredNode(asset.id, CanvasNodeType.Video, asset.title, center, size.width, size.height, {
            content: asset.url,
            storageKey: asset.storageKey,
            status: "success",
            naturalWidth: asset.width,
            naturalHeight: asset.height,
            bytes: asset.bytes,
            mimeType: asset.mimeType,
            durationMs: asset.durationMs,
        });
    }

    const spec = NODE_DEFAULT_SIZE[CanvasNodeType.Audio];
    return centeredNode(asset.id, CanvasNodeType.Audio, asset.title, center, spec.width, spec.height, {
        content: asset.url,
        storageKey: asset.storageKey,
        status: "success",
        bytes: asset.bytes,
        mimeType: asset.mimeType,
        durationMs: asset.durationMs,
    });
}

function centeredNode(id: string, type: CanvasNodeType, title: string, center: Position, width: number, height: number, metadata: CanvasNodeData["metadata"]): CanvasNodeData {
    return {
        id,
        type,
        title,
        position: { x: center.x - width / 2, y: center.y - height / 2 },
        width,
        height,
        metadata,
    };
}
