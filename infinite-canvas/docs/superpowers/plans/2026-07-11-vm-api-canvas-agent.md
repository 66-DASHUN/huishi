# VM API Canvas Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Subagents are not authorized for this repository task.

**Goal:** Deliver a tested, VM-hosted canvas AI assistant using the official OpenAI and Anthropic APIs with no Codex/Claude CLI or user-computer runtime dependency.

**Architecture:** Preserve the Huishi Flask, Next.js canvas, Nginx, and TypeScript Canvas Agent services. Put provider SDK calls, conversation persistence, authentication, and tool queues in Canvas Agent; expose it through Huishi's canvas domain and reuse the signed host session token.

**Tech Stack:** TypeScript, Express, OpenAI SDK, Anthropic SDK, Zod, Vitest, Next.js, React, Zustand, Playwright, Flask, Nginx, systemd.

---

### Task 1: Establish Test Harness And Contracts

**Files:**
- Modify: `canvas-agent/package.json`
- Modify: `canvas-agent/tsconfig.json`
- Create: `canvas-agent/vitest.config.ts`
- Create: `canvas-agent/src/agent-events.ts`
- Create: `canvas-agent/test/agent-events.test.ts`
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`
- Create: `web/src/app/(user)/canvas/stores/canvas-agent-state.ts`
- Create: `web/src/app/(user)/canvas/stores/canvas-agent-state.test.ts`

- [ ] Write failing tests for normalized turn, text delta, tool request, usage, completion, and error events.
- [ ] Run `bun test` in `canvas-agent` and confirm failures are caused by missing event normalization.
- [ ] Implement the smallest provider-neutral event types and reducer that pass.
- [ ] Add the frontend reducer tests and confirm they fail before implementation.
- [ ] Implement the frontend reducer and run both suites.

### Task 2: Add Authentication And Remove Static Browser Tokens

**Files:**
- Create: `canvas-agent/src/auth.ts`
- Create: `canvas-agent/test/auth.test.ts`
- Modify: `canvas-agent/src/http-server.ts`
- Modify: `canvas-agent/src/config.ts`
- Modify: `web/src/app/(user)/canvas/stores/use-canvas-agent-store.ts`
- Modify: `web/src/app/(user)/canvas/components/canvas-local-agent-panel.tsx`

- [ ] Write failing tests for valid, expired, missing, and rejected Huishi bearer tokens plus verification-cache expiry.
- [ ] Implement verification against the configured internal Huishi endpoint without logging token values.
- [ ] Replace EventSource query-token streaming with authenticated `fetch()` streaming.
- [ ] Remove agent URL/token persistence and default host mode to same-origin `/agent-api`.
- [ ] Run agent and frontend tests.

### Task 3: Implement Durable Conversations

**Files:**
- Create: `canvas-agent/src/conversation-store.ts`
- Create: `canvas-agent/test/conversation-store.test.ts`
- Modify: `canvas-agent/src/types.ts`
- Modify: `canvas-agent/src/http-server.ts`

- [ ] Write failing tests for create/list/read/delete, per-user isolation, atomic writes, corrupt-file recovery, and failed-turn rollback.
- [ ] Implement filesystem-backed provider-specific conversations keyed by user, canvas, and provider.
- [ ] Add provider-neutral conversation HTTP routes and remove Codex workspace/thread routes.
- [ ] Run the focused store and HTTP tests.

### Task 4: Implement Reliable Tool Queue

**Files:**
- Create: `canvas-agent/src/tool-queue.ts`
- Create: `canvas-agent/test/tool-queue.test.ts`
- Modify: `canvas-agent/src/canvas-session.ts`
- Modify: `canvas-agent/src/http-server.ts`

- [ ] Write failing tests for FIFO order, one active mutation, read-only bypass, rejection, duplicate result, timeout, disconnect, abort, and queue continuation after error.
- [ ] Implement the per-conversation queue with correlated terminal results.
- [ ] Connect queued operations to the existing canvas state/result channel.
- [ ] Run queue and CanvasSession tests.

### Task 5: Implement OpenAI Responses Adapter

**Files:**
- Create: `canvas-agent/src/providers/types.ts`
- Create: `canvas-agent/src/providers/openai-provider.ts`
- Create: `canvas-agent/test/openai-provider.test.ts`
- Modify: `canvas-agent/src/schemas.ts`
- Modify: `canvas-agent/package.json`

- [ ] Write failing mock-server tests for text streaming, strict function calls, multiple tool calls, function outputs, image inputs, usage, abort, authentication failure, rate limit, and malformed arguments.
- [ ] Add the official `openai` SDK and implement Responses API streaming with `gpt-5.6` as the configurable default.
- [ ] Preserve response output items and correlate every `function_call_output` with its `call_id`.
- [ ] Run the OpenAI adapter suite.

### Task 6: Implement Anthropic Messages Adapter

**Files:**
- Create: `canvas-agent/src/providers/anthropic-provider.ts`
- Create: `canvas-agent/test/anthropic-provider.test.ts`
- Modify: `canvas-agent/package.json`

- [ ] Write failing mock-server tests for text streaming, tool-use/result loops, multiple tool calls, image inputs, usage/cache usage, adaptive thinking configuration, abort, typed API failures, and malformed input.
- [ ] Add the official `@anthropic-ai/sdk` and implement a streaming manual tool loop with `claude-opus-4-7` as the configurable default.
- [ ] Use SDK message/tool types, stable sorted tools, full content replay, and top-level ephemeral prompt caching.
- [ ] Run the Anthropic adapter suite.

### Task 7: Replace CLI Agent Service

**Files:**
- Replace: `canvas-agent/src/agents.ts`
- Modify: `canvas-agent/src/http-server.ts`
- Modify: `canvas-agent/src/index.ts`
- Delete: `canvas-agent/src/mcp-server.ts`
- Modify: `canvas-agent/package.json`
- Modify: `canvas-agent/README.md`

- [ ] Write failing integration tests for provider selection, persisted continuation, queued tool confirmation, cancellation, and provider availability.
- [ ] Implement a provider-neutral agent service using the two adapters, conversation store, and tool queue.
- [ ] Remove `@openai/codex`, MCP runtime, spawned CLI commands, workspace directories, and CLI-facing logs/docs.
- [ ] Run all Canvas Agent tests plus `bun run build` and confirm no CLI dependency remains with a repository search.

### Task 8: Complete Canvas Assistant UI

**Files:**
- Rename: `web/src/app/(user)/canvas/components/canvas-local-agent-panel.tsx` to `canvas-api-agent-panel.tsx`
- Modify: `web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Modify: `web/src/app/(user)/canvas/stores/use-canvas-agent-store.ts`
- Modify: `web/src/app/(user)/canvas/components/canvas-agent-chat-ui.tsx`
- Modify: `web/src/lib/canvas-theme.ts`

- [ ] Write failing tests for automatic remote connection, provider selection, missing-provider messaging, streaming, one-at-a-time confirmation, reject, retry, cancel, disconnect, and undo.
- [ ] Replace local setup fields with a compact OpenAI/Claude segmented control and VM service status.
- [ ] Connect provider-neutral conversations and queue events while preserving existing canvas operation and undo logic.
- [ ] Verify light/dark themes and fixed panel dimensions without nested cards or overlapping controls.
- [ ] Run frontend tests, typecheck, and production build.

### Task 9: Deploy Secure VM Routing

**Files:**
- Create: `deploy/canvas-agent.env.example`
- Create: `deploy/huishi-canvas-agent.service`
- Create: `deploy/nginx-canvas-agent.conf`
- Modify: `docs/content/docs/overview/docker.mdx`
- Modify: `canvas-agent/README.md`

- [ ] Add deployment assertions that service binds only to loopback, secrets are absent from logs/config responses, and `/agent-api/health` is reachable through Nginx.
- [ ] Install the environment file with mode `0600`, update systemd to run the built service with an EnvironmentFile, and add Nginx `/agent-api/` proxy settings for streaming.
- [ ] Build, daemon-reload, restart, and verify `huishi`, `huishi-canvas`, and `huishi-canvas-agent` health.
- [ ] Inspect journals for warnings/errors and verify browser access requires no local process.

### Task 10: End-To-End Acceptance And Release Metadata

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/e2e/canvas-agent.spec.ts`
- Modify: `VERSION`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/content/docs/progress/todo.mdx`
- Modify: `docs/content/docs/progress/pending-test.mdx`
- Modify: `docs/content/docs/overview/features.mdx`

- [ ] Add Playwright coverage for authenticated canvas load, assistant connect, both provider mock flows, streamed response, confirmed node creation, cancellation, undo, desktop, and mobile layouts.
- [ ] Run all unit/integration tests, typecheck, production builds, and Playwright tests.
- [ ] Run deployed HTTP probes and systemd/journal checks after a clean restart.
- [ ] Move completed TODO/pending-test items according to project documentation rules and make root, package, README, and changelog versions consistent.
- [ ] Perform a requirement-by-requirement completion audit; do not declare completion while credentials are unconfigured, a provider live probe is unverified, tests fail, or a documented blocker remains.

## Execution Notes

- Project instructions prohibit commits unless the user explicitly requests one, so this plan intentionally omits commit steps.
- All project commands and deployment actions run through ordinary SSH on `huishi-vm`.
- Real provider keys are never printed. Mock-provider tests prove protocol behavior; a live provider probe is performed only when the VM is already configured with valid credentials.
