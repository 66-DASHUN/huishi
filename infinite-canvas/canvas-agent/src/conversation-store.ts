import crypto from "node:crypto";
import { mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { CONFIG_DIR } from "./config.js";

export type AgentProvider = "openai" | "anthropic";
export type ConversationMessage = {
    id: string;
    role: "user" | "assistant" | "tool" | "error";
    text: string;
    title?: string;
    detail?: unknown;
    streamId?: string;
    createdAt: number;
};
export type ConversationThread = {
    id: string;
    canvasId: string;
    provider: AgentProvider;
    title: string;
    createdAt: number;
    updatedAt: number;
    messages: ConversationMessage[];
    providerState?: Record<string, unknown>;
};

export class ConversationStore {
    constructor(
        private root = path.join(CONFIG_DIR, "conversations"),
        private now = () => Date.now(),
    ) {}

    async create(canvasId: string, provider: AgentProvider) {
        const time = this.now();
        const thread: ConversationThread = {
            id: crypto.randomUUID(),
            canvasId: safeSegment(canvasId || "default"),
            provider,
            title: "新会话",
            createdAt: time,
            updatedAt: time,
            messages: [],
        };
        await this.write(thread);
        return thread;
    }

    async list(canvasId: string, provider: AgentProvider) {
        await mkdir(this.root, { recursive: true });
        const names = await readdir(this.root);
        const threads = await Promise.all(names.filter((name) => name.endsWith(".json")).map((name) => this.readFile(path.join(this.root, name))));
        const safeCanvasId = safeSegment(canvasId || "default");
        return threads
            .filter((thread): thread is ConversationThread => Boolean(thread && thread.canvasId === safeCanvasId && thread.provider === provider))
            .sort((a, b) => b.updatedAt - a.updatedAt)
            .map(summarizeThread);
    }

    async read(id: string) {
        const thread = await this.readFile(this.file(id));
        if (!thread) throw new Error("会话不存在");
        return thread;
    }

    async appendMessages(id: string, messages: ConversationMessage[]) {
        const thread = await this.read(id);
        const next = { ...thread, messages: [...thread.messages, ...messages], updatedAt: this.now() };
        const firstUserText = next.messages.find((message) => message.role === "user")?.text.trim();
        if (thread.title === "新会话" && firstUserText) next.title = firstUserText.slice(0, 60);
        await this.write(next);
        return next;
    }

    async updateState(id: string, providerState: Record<string, unknown>) {
        const thread = await this.read(id);
        const next = { ...thread, providerState, updatedAt: this.now() };
        await this.write(next);
        return next;
    }

    async delete(id: string) {
        await rm(this.file(id), { force: true });
    }

    private file(id: string) {
        return path.join(this.root, `${safeSegment(id)}.json`);
    }

    private async readFile(file: string) {
        try {
            return JSON.parse(await readFile(file, "utf8")) as ConversationThread;
        } catch {
            return null;
        }
    }

    private async write(thread: ConversationThread) {
        await mkdir(this.root, { recursive: true });
        const file = this.file(thread.id);
        const temporary = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`;
        await writeFile(temporary, `${JSON.stringify(thread, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
        await rename(temporary, file);
    }
}

function summarizeThread(thread: ConversationThread) {
    return {
        id: thread.id,
        provider: thread.provider,
        canvasId: thread.canvasId,
        title: thread.title,
        preview: thread.messages.at(-1)?.text.slice(0, 120) || "",
        createdAt: thread.createdAt,
        updatedAt: thread.updatedAt,
    };
}

function safeSegment(value: string) {
    return value.replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 120) || "default";
}
