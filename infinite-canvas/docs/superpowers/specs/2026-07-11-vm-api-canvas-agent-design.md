# VM API Canvas Agent Design

## Goal

Deliver a stable personal Huishi deployment in which the browser, canvas UI, Huishi host, and AI agent remain usable while the user's Windows computer is offline. All runtime services live on `huishi-vm`; neither Codex nor Claude CLI/app-server is a runtime dependency.

## Scope

- Keep the existing Next.js canvas, Huishi Flask host, Nginx, and TypeScript Canvas Agent service boundaries.
- Replace `@openai/codex` and spawned `claude` commands with the official `openai` and `@anthropic-ai/sdk` packages.
- Support OpenAI Responses API and Anthropic Messages API with streaming text, image attachments, multi-turn conversations, usage reporting, and canvas function tools.
- Run all services under systemd on `huishi-vm:/opt/huishi`; browser clients use the Huishi site only.
- Retain current canvas, image generation, material library, host session, and WebDAV behavior and add automated regression coverage around their stable contracts.
- Exclude public multi-tenant hosting, cloud canvas storage, billing redesign, and user-managed provider keys from this delivery.

## Runtime Architecture

1. A browser opens `https://huishi.local/canvas`, which embeds `https://canvas.huishi.local/canvas`.
2. Huishi issues the existing signed canvas session token and passes it to the embedded canvas bootstrap.
3. The canvas calls same-origin `https://canvas.huishi.local/agent-api/*`; Nginx proxies that prefix to Canvas Agent on `127.0.0.1:17371`.
4. Canvas Agent validates every request token through the internal Huishi verification endpoint before accepting state, events, conversation, or tool traffic.
5. Canvas Agent calls OpenAI or Anthropic directly from the VM, using keys loaded from a root-managed environment file. Keys never enter browser storage, URLs, response bodies, or logs.
6. Model tool calls enter a per-conversation FIFO queue. The browser renders one confirmation at a time, executes approved canvas operations, and returns a correlated result. Rejections and failures are returned to the provider loop as tool errors.

## Provider Design

Canvas Agent exposes a provider-neutral conversation service and two focused adapters:

- OpenAI adapter: official `openai` SDK, Responses API, `gpt-5.6` default, typed streaming events, strict function schemas, manual replay of response items and `function_call_output` items.
- Anthropic adapter: official `@anthropic-ai/sdk`, `claude-opus-4-7` default, streaming manual tool loop, SDK types, adaptive thinking, stable tools/system prefix, and top-level ephemeral prompt caching.

Both adapters normalize provider events into the existing browser event vocabulary: turn start, text delta, tool request, usage, completion, and error. Provider-specific response objects are retained server-side as conversation state and are never treated as interchangeable wire formats.

## Conversation Persistence

- Conversations are keyed by verified Huishi user ID, canvas project ID, provider, and conversation ID.
- Metadata and provider history are written atomically under a VM-owned Canvas Agent data directory.
- The API supports list, create, read, continue, and delete operations.
- A bounded transcript and attachment policy prevents unbounded disk growth. Attachments are decoded to temporary files or provider-native image blocks and deleted after the turn.
- A failed turn leaves the previous durable conversation intact; only completed provider steps are persisted.

## Authentication And Secrets

- Browser requests send the existing Huishi canvas session token in an `Authorization: Bearer` header. Streaming uses `fetch()` so the token is not placed in the SSE URL.
- Canvas Agent verifies the token against `http://127.0.0.1:8000/api/canvas/session/verify` and caches successful verification only until the token expiry, with a short upper bound.
- Canvas Agent listens only on `127.0.0.1`; Nginx is its only public ingress.
- `/etc/huishi/canvas-agent.env` is mode `0600` and contains `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and internal URL/origin settings.
- Health/config endpoints report only provider availability and model names, never keys or static connection tokens.

## Tool Queue

- Each conversation owns a FIFO queue with at most one active browser confirmation.
- Read-only state tools may execute immediately; mutating tools require confirmation by default.
- Every queued request has an ID, status, enqueue time, expiry, and exactly one terminal result.
- Cancellation, timeout, disconnect, duplicate result, and provider abort paths are explicit and tested.
- A successful canvas mutation stores one undo snapshot in the existing UI. Queue advancement never depends on a React render race.

## UI Changes

- Replace “本地 Agent” wording and manual localhost/token fields with “画布 AI 助手”.
- Auto-connect in authenticated Huishi host mode using `/agent-api` and the verified host token.
- Add an OpenAI/Claude segmented provider control, server availability state, conversation history, streaming response, queued tool confirmation, cancel/retry, and actionable configuration errors.
- Keep the existing compact canvas theme, fixed panel dimensions, and current undo behavior.
- Do not store VM API keys or agent authentication tokens in `localStorage`.

## Error Handling

- Map SDK authentication, rate-limit, timeout, abort, malformed tool input, and upstream server failures to stable error codes plus concise Chinese UI messages.
- Log request IDs, provider, model, conversation ID, latency, and token usage, but never prompts, image data, session tokens, or API keys by default.
- Provider failure cannot block later queue entries permanently; disconnect fails active browser work and keeps durable conversation state consistent.

## Verification

- Canvas Agent unit tests cover authentication, persistence, provider event normalization, strict tools, caching configuration, tool-result correlation, queue ordering, timeout, cancellation, and secret redaction.
- Frontend tests cover host-mode auto-connect, provider switching, streaming reducer behavior, confirmation queue, retry, disconnect, and absence of token persistence.
- Integration tests use local mock OpenAI, Anthropic, and Huishi verification servers; no paid API key is required for CI.
- Playwright covers Huishi login-to-canvas load, assistant connection, streamed response, confirmed node creation, cancellation, undo, and mobile/desktop panel layout.
- Release verification includes typecheck, tests, production build, systemd health, Nginx routing, HTTP probes, and journal warning/error review.

## Release Criteria

The release is complete only when both provider adapters pass mocked end-to-end tool loops, the deployed VM services remain healthy after restart, the browser requires no local process, all documented pending tests are either automated or manually recorded as passed, version metadata is consistent, and no known blocker remains in the project TODO.
