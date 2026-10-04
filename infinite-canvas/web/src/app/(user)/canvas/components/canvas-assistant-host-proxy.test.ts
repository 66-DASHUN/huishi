import { expect, test } from "bun:test";
import { CanvasNodeType, type CanvasAssistantMessage, type CanvasAssistantReference } from "../types";
import type { CanvasAgentSnapshot } from "../utils/canvas-agent-ops";
import { buildToolAgentMessages, findRetryReferences, formatHostChatError } from "../utils/canvas-agent-messages";

const references: CanvasAssistantReference[] = [
    { id: "image-1", type: CanvasNodeType.Image, title: "Reference one", dataUrl: "data:image/png;base64,AAAA" },
    { id: "image-2", type: CanvasNodeType.Image, title: "Reference two", dataUrl: "data:image/png;base64,BBBB" },
];
const snapshot: CanvasAgentSnapshot = {
    title: "Test canvas",
    viewport: { x: 0, y: 0, k: 1 },
    selectedNodeIds: references.map((reference) => reference.id),
    nodes: [],
    connections: [],
};
const userMessage: CanvasAssistantMessage = { id: "user-1", role: "user", text: "create images", references };

function userContent(messages: Awaited<ReturnType<typeof buildToolAgentMessages>>) {
    const message = messages[messages.length - 1];
    if (!("role" in message) || message.role !== "user" || !Array.isArray(message.content)) throw new Error("Expected user content parts");
    return message.content;
}

test("host Agent proxy keeps reference metadata but omits image payloads", async () => {
    const messages = await buildToolAgentMessages(snapshot, [], userMessage, {
        systemPrompt: "system",
        includeReferenceImages: false,
        resolveReferenceImage: async () => {
            throw new Error("host proxy must not resolve image data");
        },
    });
    const content = userContent(messages);
    const text = content.filter((item) => item.type === "text").map((item) => item.text);

    expect(content.filter((item) => item.type === "image_url")).toHaveLength(0);
    expect(text.some((item) => item.includes("image-1") && item.includes("image"))).toBe(true);
    expect(text.some((item) => item.includes("image-2") && item.includes("image"))).toBe(true);
});

test("direct visual providers retain both reference images", async () => {
    const messages = await buildToolAgentMessages(snapshot, [], userMessage, {
        systemPrompt: "system",
        includeReferenceImages: true,
        resolveReferenceImage: async (reference) => reference.dataUrl || "",
    });

    expect(userContent(messages).filter((item) => item.type === "image_url")).toHaveLength(2);
});

test("host Agent proxy maps provider payload errors to concise Chinese", async () => {
    const message = formatHostChatError("unknown variant image_url, expected text while deserializing");
    expect(message).toBe("\u5f53\u524d\u6587\u672c\u6a21\u578b\u4e0d\u652f\u6301\u76f4\u63a5\u8bc6\u522b\u53c2\u8003\u56fe\uff0c\u5df2\u6539\u7528\u753b\u5e03\u4e2d\u7684\u53c2\u8003\u4fe1\u606f\u3002");
});

test("retry restores the references from the failed user message", async () => {
    const messages: CanvasAssistantMessage[] = [
        userMessage,
        { id: "assistant-1", role: "assistant", text: "working" },
        { id: "error-1", role: "error", text: "failed" },
    ];

    expect(findRetryReferences(messages, "error-1", "create images")).toEqual(references);
    expect(findRetryReferences(messages, "missing", "create images")).toEqual([]);
});
