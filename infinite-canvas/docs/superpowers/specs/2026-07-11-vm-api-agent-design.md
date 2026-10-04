# VM API Agent Design

## Scope

The Huishi deployment remains a personal VM-hosted application. The browser must not start or depend on local Codex or Claude executables. OpenAI and Anthropic requests, API keys, conversation state, tool scheduling, and provider error handling run on `huishi-vm`.

## Architecture

- Nginx and Huishi remain the authenticated same-origin entry point.
- The Next.js canvas continues to execute canvas operations in the browser because canvas state is browser-owned.
- `canvas-agent` remains a private VM service and replaces CLI adapters with official OpenAI and Anthropic SDK adapters.
- Model tools use the existing typed canvas tool schemas. Read tools execute immediately; mutating tools are sent to the browser confirmation UI and are serialized per conversation.
- Provider credentials come from VM environment variables and are never returned by `/config`, written to browser storage, included in URLs, or logged.

## Conversation Model

Conversation history is persisted per canvas and provider under the Canvas Agent data directory. Threads can be listed, created, read, resumed, and deleted. A failed turn keeps the previous committed history intact and emits a retryable error.

## Provider Contracts

- OpenAI uses the official SDK and Responses API with streaming and function tools.
- Anthropic uses the official SDK and Messages API with streaming, a manual tool loop for confirmation control, stable tool ordering, and prompt caching.
- Both providers emit the same browser events: `thread.started`, `turn.started`, `item.updated`, tool status events, `turn.completed`, and `turn.failed`.

## Reliability

- One active turn per thread; later turns queue in arrival order.
- Tool calls have explicit timeout and structured error results.
- Conversation files are written atomically.
- API authentication, rate-limit, overload, timeout, invalid model, and missing-key failures are normalized into Chinese user-facing messages without leaking provider response bodies or keys.

## Verification

Automated tests cover storage isolation, queue ordering, provider event normalization, tool-loop success/error behavior, HTTP authorization, and core frontend interactions. Deployment verification covers systemd health, same-origin access, an OpenAI text turn, a Claude text turn, one confirmed canvas mutation, rejection, retry, and service restart persistence.
