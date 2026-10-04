# Collaboration Protocol

## Roles

| Role | Responsibilities |
| --- | --- |
| User | Sets goals, accepts tradeoffs, approves destructive or deployment-impacting operations. |
| Codex | Coordinates the thread, edits code, runs commands/tests, integrates review feedback, reports status in Simplified Chinese. |
| Claude | Advises Codex through planning, risk checks, code review, and PR/release-note drafting. Claude does not edit files by default. |

## Default Flow

1. User sends a normal requirement in the Codex thread.
2. Codex inspects the current repository state.
3. For complex, risky, cross-file, database, deployment, billing, security, or ambiguous work, Codex asks Claude for a concise plan or risk check.
4. Codex implements the agreed change.
5. Codex runs targeted and, when needed, full verification.
6. For non-trivial diffs, Codex asks Claude for review.
7. Codex fixes Claude findings marked `BLOCKER` or relevant `SHOULD_FIX`.
8. Codex reports final outcome, verification, and remaining risks to the user.

## Review Rules

- Claude review findings are advisory, but `BLOCKER` findings must be resolved or explicitly accepted by the user.
- Codex should summarize Claude output instead of dumping long transcripts.
- If Claude is unavailable or times out, Codex may proceed from local evidence and must say so.
- If Codex and Claude disagree, Codex should explain the tradeoff and choose the safer path unless the user directs otherwise.

## Architecture Decision Rules

- Prefer incremental phases over broad rewrites.
- Keep SQLite production hardening separate from PostgreSQL migration.
- Do not introduce Redis or a queue until the current in-process generation model and database state transitions are documented.
- Ubuntu deployability is a release requirement for backend architecture changes.
- Every architecture phase needs an acceptance checklist and rollback path.
