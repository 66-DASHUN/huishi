# VM API Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace local Codex/Claude executable adapters with VM-hosted OpenAI and Anthropic API adapters while preserving confirmed canvas tool execution.

**Architecture:** Keep `canvas-agent` as a private TypeScript service. Add an atomic per-canvas conversation store, provider adapters behind one runtime contract, and per-thread serialization. Preserve the existing CanvasSession tool bridge so browser confirmation remains authoritative.

**Tech Stack:** TypeScript, Express, Zod, Node test runner through `tsx`, official `openai` SDK, official `@anthropic-ai/sdk`.

---

### Task 1: Persistent Conversation Store

**Files:**
- Create: `canvas-agent/src/conversation-store.ts`
- Create: `canvas-agent/test/conversation-store.test.ts`
- Modify: `canvas-agent/package.json`

- [ ] Write tests for provider/canvas isolation, message persistence, updated-time ordering, and deletion.
- [ ] Run `bun run test` and confirm failure because `conversation-store.ts` does not exist.
- [ ] Implement `ConversationStore` with atomic temporary-file rename and safe path segments.
- [ ] Run `bun run test` and confirm all store tests pass.

### Task 2: Per-Thread Turn Queue

**Files:**
- Create: `canvas-agent/src/turn-queue.ts`
- Create: `canvas-agent/test/turn-queue.test.ts`

- [ ] Test same-thread serialization, cross-thread concurrency, and recovery after a rejected turn.
- [ ] Run the focused test and confirm the missing module failure.
- [ ] Implement a promise-chain map keyed by thread ID and remove idle chains.
- [ ] Run the focused and full test suites.

### Task 3: Provider-Neutral Runtime Contract

**Files:**
- Create: `canvas-agent/src/agent-runtime.ts`
- Create: `canvas-agent/src/provider-tools.ts`
- Create: `canvas-agent/test/provider-tools.test.ts`

- [ ] Test deterministic tool ordering and conversion of existing Zod schemas to provider tool definitions.
- [ ] Implement shared turn/event/tool contracts and validated tool execution through `CanvasSession.callTool`.
- [ ] Verify tests pass.

### Task 4: OpenAI Responses Adapter

**Files:**
- Create: `canvas-agent/src/providers/openai-provider.ts`
- Create: `canvas-agent/test/openai-provider.test.ts`
- Modify: `canvas-agent/package.json`

- [ ] Add fake-client tests for text deltas, function calls, tool outputs, usage, API errors, and aborted streams.
- [ ] Add the official `openai` SDK.
- [ ] Implement Responses API streaming and the manual function-tool loop.
- [ ] Verify focused and full tests.

### Task 5: Anthropic Messages Adapter

**Files:**
- Create: `canvas-agent/src/providers/anthropic-provider.ts`
- Create: `canvas-agent/test/anthropic-provider.test.ts`
- Modify: `canvas-agent/package.json`

- [ ] Add fake-client tests for streaming text, multiple tool calls, tool errors, usage/cache metrics, and typed API failures.
- [ ] Add the official `@anthropic-ai/sdk`.
- [ ] Implement a manual streaming tool loop with stable tools, full content preservation, and top-level ephemeral prompt caching.
- [ ] Verify focused and full tests.

### Task 6: HTTP API Migration

**Files:**
- Modify: `canvas-agent/src/http-server.ts`
- Modify: `canvas-agent/src/config.ts`
- Create: `canvas-agent/test/http-server.test.ts`

- [ ] Test provider health metadata, authorization, generic thread routes, and missing-key behavior.
- [ ] Replace Codex-specific routes with `/agent/:provider/...` routes while retaining temporary compatibility aliases.
- [ ] Stop logging connection tokens and provider secrets.
- [ ] Verify tests.

### Task 7: Canvas Sidebar Migration

**Files:**
- Modify: `web/src/app/(user)/canvas/components/canvas-local-agent-panel.tsx`
- Modify: `web/src/app/(user)/canvas/components/canvas-agent-chat-ui.tsx`
- Modify: `web/src/app/(user)/canvas/stores/use-canvas-agent-store.ts`

- [ ] Add component/store tests for provider switching, queued mutation confirmation, rejection, retry, and reconnect.
- [ ] Rename local/Codex concepts to VM API provider concepts and call the generic routes.
- [ ] Keep the compact existing canvas theme and tool cards.
- [ ] Verify frontend tests.

### Task 8: Deployment and Release Verification

**Files:**
- Modify: `canvas-agent/README.md`
- Modify: `docs/content/docs/progress/todo.mdx`
- Modify: `docs/content/docs/progress/pending-test.mdx`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`
- Modify: VM systemd/nginx configuration as required

- [ ] Document VM environment variables and same-origin routes without secret values.
- [ ] Restart services and verify health endpoints.
- [ ] Verify OpenAI and Claude text turns, confirmed/rejected canvas tools, restart persistence, Gemini, WebDAV, and Huishi host mode.
- [ ] Move completed items from TODO to pending-test and reconcile all version strings.
