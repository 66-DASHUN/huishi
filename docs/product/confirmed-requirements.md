# Confirmed Requirements

This file records requirements that are confirmed by the user in the Codex thread.

## Operating Model

- The Codex thread is the user's main interface.
- The user can send normal requirements without a special "AI collaboration" prefix.
- Codex decides when Claude should be used.
- Claude is advisory by default: planning, risk analysis, review, and PR-description drafting.
- Codex owns code edits, commands, tests, commits, and final user reporting.

## Architecture Direction

- The project should move toward a production-ready architecture that can later use PostgreSQL, Redis, and an external task queue.
- The architecture must remain deployable on an Ubuntu server.
- The first production step should be safe and incremental, not a broad immediate rewrite.
- Current P0 direction: make the existing Flask + SQLite app deployable with Gunicorn, systemd, Nginx, and SQLite production hardening.
- PostgreSQL/Redis migration should happen in later phases after the current codebase is stabilized and database access is better isolated.

## Current Production Implementation (2026-07-12)

- The historical SQLite P0 was completed and the Ubuntu VM has since advanced to PostgreSQL, Redis, RQ workers, Gunicorn, Nginx HTTPS, Next.js canvas, and a sandboxed Canvas Agent.
- SQLite remains the local-development and default unit-test fallback. Production requires PostgreSQL and Redis through explicit startup guards.
- A dedicated PostgreSQL test profile now resets an isolated test schema before every test and refuses database names that do not contain `test`, `pytest`, or `rehearsal`.
- The production database has fresh backup/checksum evidence and a successful isolated restore rehearsal with the matching encryption key.

## Safety Constraints

- Do not revert user changes unless explicitly requested.
- Do not commit, push, or create a PR unless explicitly requested.
- Broad migrations, destructive data operations, and deployment-impacting changes require explicit user confirmation.
- Run relevant verification before claiming work is complete.
