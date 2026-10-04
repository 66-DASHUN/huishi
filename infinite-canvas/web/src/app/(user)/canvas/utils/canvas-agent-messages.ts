import type { ResponseInputMessage } from "@/services/api/image";

import type { CanvasAssistantMessage, CanvasAssistantReference, CanvasNodeData } from "../types";
import type { CanvasAgentSnapshot } from "./canvas-agent-ops";

type BuildToolAgentMessageOptions = {
    systemPrompt: string;
    includeReferenceImages: boolean;
    resolveReferenceImage: (reference: CanvasAssistantReference) => Promise<string>;
};

export function formatHostChatError(message: string) {
    if (/image_url/i.test(message) && /deserialize|expected.*text/i.test(message)) {
        return "\u5f53\u524d\u6587\u672c\u6a21\u578b\u4e0d\u652f\u6301\u76f4\u63a5\u8bc6\u522b\u53c2\u8003\u56fe\uff0c\u5df2\u6539\u7528\u753b\u5e03\u4e2d\u7684\u53c2\u8003\u4fe1\u606f\u3002";
    }
    return "\u5bf9\u8bdd\u6a21\u578b\u8bf7\u6c42\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002";
}

export function findRetryReferences(messages: CanvasAssistantMessage[], errorMessageId: string, retryText: string) {
    const errorIndex = messages.findIndex((message) => message.id === errorMessageId);
    if (errorIndex <= 0) return [];
    return (
        messages
            .slice(0, errorIndex)
            .reverse()
            .find((message) => message.role === "user" && message.text.trim() === retryText)?.references || []
    );
}

export async function buildToolAgentMessages(
    snapshot: CanvasAgentSnapshot,
    history: CanvasAssistantMessage[],
    userMessage: CanvasAssistantMessage,
    options: BuildToolAgentMessageOptions,
): Promise<ResponseInputMessage[]> {
    const refs = userMessage.references || [];
    const canvasContext = shouldIncludeCanvasSnapshot(userMessage.text) ? `\u5f53\u524d\u753b\u5e03\uff1a${JSON.stringify(compactCanvasSnapshot(snapshot))}` : "";
    const imageParts = options.includeReferenceImages
        ? await Promise.all(
              refs.filter((item) => item.dataUrl).map(async (item) => ({ type: "image_url" as const, image_url: { url: await options.resolveReferenceImage(item) } })),
          )
        : [];
    return [
        { role: "system", content: options.systemPrompt },
        ...history
            .filter((message): message is CanvasAssistantMessage & { role: "user" | "assistant" | "system" } => message.role === "user" || message.role === "assistant" || message.role === "system")
            .slice(-8)
            .map((message): ResponseInputMessage => ({ role: message.role, content: message.text })),
        {
            role: "user",
            content: [
                ...refs.map((item) => ({
                    type: "text" as const,
                    text: `\u7528\u6237\u663e\u5f0f\u9009\u4e2d\u8282\u70b9 ${item.title}\uff08id: ${item.id}\uff0c\u7c7b\u578b: ${item.type}\uff09${item.text ? `\uff1a${item.text}` : ""}`,
                })),
                { type: "text", text: `\u7528\u6237\u9700\u6c42\uff1a${userMessage.text}` },
                ...(canvasContext ? [{ type: "text" as const, text: canvasContext }] : []),
                ...imageParts,
            ],
        },
    ];
}

function shouldIncludeCanvasSnapshot(text: string) {
    return /\u753b\u5e03|\u8282\u70b9|\u8fde\u7ebf|\u5e03\u5c40|\u89c6\u56fe|\u7f29\u653e|\u9009\u4e2d|\u6574\u7406|\u6e05\u7406|\u6e05\u7a7a|\u5220\u9664|\u79fb\u52a8|\u8fde\u63a5|\u65ad\u5f00|\u91cd\u547d\u540d|\u5bfc\u51fa/.test(text);
}

export function compactCanvasSnapshot(snapshot: CanvasAgentSnapshot) {
    return {
        title: snapshot.title,
        viewport: snapshot.viewport,
        selectedNodeIds: snapshot.selectedNodeIds,
        nodes: snapshot.nodes.map((node) => ({
            id: node.id,
            type: node.type,
            title: node.title,
            position: node.position,
            width: node.width,
            height: node.height,
            metadata: compactMetadata(node.metadata || {}),
        })),
        connections: snapshot.connections,
    };
}

function compactMetadata(metadata: CanvasNodeData["metadata"]) {
    return {
        content: String(metadata?.content || "").slice(0, 500),
        prompt: String(metadata?.prompt || metadata?.composerContent || "").slice(0, 500),
        status: metadata?.status,
        generationMode: metadata?.generationMode,
        model: metadata?.model,
        size: metadata?.size,
    };
}
