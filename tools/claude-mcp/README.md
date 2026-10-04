# claude-mcp-server

Local stdio MCP bridge for asking Claude CLI to advise Codex.

## Tools

- `claude_plan`: requirement analysis, implementation plan, acceptance criteria, risks, and suggested tests.
- `claude_review`: review a Codex-produced diff or implementation summary.
- `claude_pr_description`: draft a PR description from the requirement, summary, tests, and diff.
- `claude_plan_async`: start a long-running planning job and return a `job_id` immediately.
- `claude_review_async`: start a long-running review job and return a `job_id` immediately.
- `claude_pr_description_async`: start a long-running PR-description job and return a `job_id` immediately.
- `claude_job_status`: poll an async job until it returns `succeeded` or `failed`.

All tools call `claude -p` in read-only advisory mode. Codex remains responsible for editing files and running commands.

Use the async tools for large diffs or long reviews. `CLAUDE_MCP_TIMEOUT_MS=1800000` lets the bridge keep Claude CLI running for 30 minutes, while async tools avoid the Codex app's per-call `tools/call` timeout by returning immediately and polling later.

## Build

```powershell
npm install
npm run build
```

## Codex config

Point Codex at the built server:

```toml
[mcp_servers.claude_bridge]
command = "node"
args = ["D:\\AI\\huishihuabu\\tools\\claude-mcp\\dist\\index.js"]
startup_timeout_sec = 120

[mcp_servers.claude_bridge.env]
CLAUDE_MCP_CWD = "D:\\AI\\huishihuabu"
CLAUDE_CLI_PATH = "E:\\Phthon learning space\\tools\\Node\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"
CLAUDE_MCP_TIMEOUT_MS = "1800000"
```
