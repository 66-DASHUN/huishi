import { expect, test } from "bun:test";

import { assetToCanvasNode } from "./canvas-asset-insertion";
import { CanvasNodeType } from "../types";

test("video asset preserves aspect ratio and centers in the viewport", () => {
    const node = assetToCanvasNode({ kind: "video", id: "video-1", title: "Demo", url: "/demo.mp4", width: 1920, height: 1080 }, { x: 500, y: 400 });

    expect(node.type).toBe(CanvasNodeType.Video);
    expect(node.metadata?.naturalWidth).toBe(1920);
    expect(node.metadata?.naturalHeight).toBe(1080);
    expect(node.width).toBe(420);
    expect(node.height).toBeCloseTo(236.25);
    expect(node.position.x + node.width / 2).toBe(500);
    expect(node.position.y + node.height / 2).toBe(400);
});

test("text asset keeps text metadata and the default centered size", () => {
    const node = assetToCanvasNode({ kind: "text", id: "text-1", title: "Note", content: "hello" }, { x: 100, y: 200 });

    expect(node).toMatchObject({
        id: "text-1",
        type: CanvasNodeType.Text,
        title: "Note",
        position: { x: -70, y: 80 },
        width: 340,
        height: 240,
        metadata: { content: "hello", status: "success", fontSize: 14 },
    });
});

test("image and audio assets preserve storage metadata", () => {
    const image = assetToCanvasNode({ kind: "image", id: "image-1", title: "Image", url: "/image.webp", storageKey: "image:key", width: 1200, height: 600, bytes: 42, mimeType: "image/webp", prompt: "prompt" }, { x: 0, y: 0 });
    const audio = assetToCanvasNode({ kind: "audio", id: "audio-1", title: "Audio", url: "/audio.mp3", storageKey: "media:key", bytes: 84, mimeType: "audio/mpeg", durationMs: 1200 }, { x: 10, y: 20 });

    expect(image).toMatchObject({ width: 640, height: 320, metadata: { storageKey: "image:key", bytes: 42, mimeType: "image/webp", prompt: "prompt" } });
    expect(audio).toMatchObject({ type: CanvasNodeType.Audio, position: { x: -160, y: -40 }, metadata: { storageKey: "media:key", bytes: 84, mimeType: "audio/mpeg", durationMs: 1200 } });
});
