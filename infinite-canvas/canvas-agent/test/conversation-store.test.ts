import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { ConversationStore } from "../src/conversation-store.js";

test("persists and isolates conversations by canvas and provider", async (t) => {
    const root = await mkdtemp(path.join(os.tmpdir(), "canvas-agent-store-"));
    t.after(() => rm(root, { recursive: true, force: true }));
    const store = new ConversationStore(root);

    const openai = await store.create("canvas-a", "openai");
    const anthropic = await store.create("canvas-a", "anthropic");
    await store.appendMessages(openai.id, [
        { id: "u1", role: "user", text: "hello", createdAt: 10 },
        { id: "a1", role: "assistant", text: "world", createdAt: 11 },
    ]);

    assert.equal((await store.read(openai.id)).messages.length, 2);
    assert.deepEqual((await store.list("canvas-a", "openai")).map((thread) => thread.id), [openai.id]);
    assert.deepEqual((await store.list("canvas-a", "anthropic")).map((thread) => thread.id), [anthropic.id]);
    assert.deepEqual(await store.list("canvas-b", "openai"), []);
});

test("lists most recently updated conversations first and deletes them", async (t) => {
    const root = await mkdtemp(path.join(os.tmpdir(), "canvas-agent-store-"));
    t.after(() => rm(root, { recursive: true, force: true }));
    let now = 100;
    const store = new ConversationStore(root, () => ++now);

    const first = await store.create("canvas-a", "openai");
    const second = await store.create("canvas-a", "openai");
    await store.appendMessages(first.id, [{ id: "u1", role: "user", text: "newest", createdAt: now }]);

    assert.deepEqual((await store.list("canvas-a", "openai")).map((thread) => thread.id), [first.id, second.id]);
    await store.delete(first.id);
    await assert.rejects(() => store.read(first.id), /会话不存在/);
});
