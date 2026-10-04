import { expect, test } from "bun:test";

import { buildNodeGenerationContext } from "./canvas-node-generation";
import { CanvasNodeType } from "../types";

const sourceImage = (id: string, title: string) => ({
    id,
    type: CanvasNodeType.Image,
    title,
    position: { x: 0, y: 0 },
    width: 100,
    height: 100,
    metadata: { content: `https://assets.test/${id}.png`, mimeType: "image/png" },
});

const videoTarget = {
    id: "video-target",
    type: CanvasNodeType.Video,
    title: "Video",
    position: { x: 300, y: 0 },
    width: 100,
    height: 100,
};

test("a structured @ mention sends only its bound resource to generation", () => {
    const nodes = [sourceImage("image-a", "front.png"), sourceImage("image-b", "side.png"), videoTarget];
    const connections = nodes.slice(0, 2).map((node) => ({ id: `connection-${node.id}`, fromNodeId: node.id, toNodeId: videoTarget.id }));

    const context = buildNodeGenerationContext(videoTarget.id, nodes, connections, "Use @[node:image-b] as the subject");

    expect(context.referenceImages.map((image) => image.id)).toEqual(["image-b"]);
    expect(context.prompt).toContain("图片1");
    expect(context.prompt).not.toContain("@[node:");
});

test("without a structured @ mention, existing connected-resource behavior is preserved", () => {
    const nodes = [sourceImage("image-a", "front.png"), sourceImage("image-b", "side.png"), videoTarget];
    const connections = nodes.slice(0, 2).map((node) => ({ id: `connection-${node.id}`, fromNodeId: node.id, toNodeId: videoTarget.id }));

    const context = buildNodeGenerationContext(videoTarget.id, nodes, connections, "Use the connected references");

    expect(context.referenceImages.map((image) => image.id)).toEqual(["image-a", "image-b"]);
});
