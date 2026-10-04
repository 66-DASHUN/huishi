# SQL Inventory

This inventory starts Phase P1: Database Access Boundary. It records the current SQL surface before PostgreSQL compatibility work begins.

Last updated: 2026-07-08

## Summary

- Database engine in current code: SQLite through Python `sqlite3`.
- Shared connection entrypoint: `huishi/db.py:get_db()`.
- Direct `sqlite3.connect` usage: only `huishi/db.py`.
- SQLite PRAGMA setup: only `huishi/db.py`.
- SQL callers are still spread across routes and domain modules. This is expected before P1 refactoring, but it is the main reason PostgreSQL migration should not start yet.

## Main SQL Modules

| Module | SQL role | Main tables |
| --- | --- | --- |
| `huishi/db.py` | Schema creation, migrations, seed defaults, SQLite connection configuration | all tables |
| `huishi/auth.py` | Login, registration, verification, password reset | `users` |
| `huishi/billing.py` | Balance checks, point ledger writes, billing deductions | `users`, `point_ledger`, `generation_tasks` |
| `huishi/invites.py` | Invite creation and redemption | `invite_codes`, `invite_redemptions`, `app_settings` |
| `huishi/providers.py` | App settings and API provider configuration | `app_settings`, `api_providers` |
| `huishi/records.py` | Dialogues, records, generation task state transitions | `dialogues`, `records`, `generation_tasks` |
| `huishi/routes_admin.py` | Admin dashboard, config, billing, packages, users, bulk import/delete | `users`, `records`, `generation_tasks`, `point_ledger`, `packages`, `pricing_rules`, `invite_codes`, `invite_redemptions`, `canvas_*` |
| `huishi/routes_workspace.py` | Workspace generation flow, canvas APIs, asset operations | `users`, `records`, `dialogues`, `generation_tasks`, `api_providers`, `canvas_conversations`, `canvas_messages` |
| `app.py` | Read-only home/account/pricing queries | `point_ledger`, `invite_codes`, `pricing_rules`, `packages` |
| `huishi/user_key.py` | User-owned provider credentials | `user_settings` |

## SQLite-Specific Constructs

These constructs need explicit handling before PostgreSQL compatibility can be claimed.

| Construct | Current location | PostgreSQL Compatibility Risks |
| --- | --- | --- |
| `AUTOINCREMENT` | `huishi/db.py` schema definitions | PostgreSQL uses `GENERATED ... AS IDENTITY` or `SERIAL`; migration must map primary keys explicitly. |
| `INSERT OR IGNORE` | `huishi/db.py:seed_defaults` | PostgreSQL equivalent is `ON CONFLICT DO NOTHING`; conflict targets must be explicit. |
| `PRAGMA` | `huishi/db.py` connection setup and migrations | SQLite-only. PostgreSQL needs separate session settings and schema inspection. |
| `PRAGMA table_info(...)` | migration helpers in `huishi/db.py` | PostgreSQL must use `information_schema` or migration tool state instead. |
| Partial unique index `WHERE email != ''` | `migrate_users_table` | PostgreSQL supports partial indexes, but empty-string semantics must be preserved. |
| `BEGIN IMMEDIATE` | `huishi/routes_workspace.py` generation creation flow | SQLite lock behavior. PostgreSQL should use transaction isolation or row-level locks. |
| `lastrowid` | `auth.py`, `providers.py`, `records.py`, `routes_workspace.py` | PostgreSQL needs `RETURNING id` or driver-specific returned IDs. |
| `?` placeholders | all SQL callers | psycopg uses `%s` or named placeholders unless wrapped by an adapter layer. |
| `COALESCE(NULLIF(...))` | `records.py`, task dismissal | SQL is portable, but should be covered by tests before migration. |
| string timestamps | all tables | PostgreSQL may use `TIMESTAMPTZ`; migration must normalize existing ISO strings. |

## High-Risk Write Paths

These paths must stay covered by tests while P1/P2 refactoring proceeds.

| Path | Current coverage | Risk |
| --- | --- | --- |
| User deletion cascade | `tests/test_admin_delete_user_cascade.py` | Foreign-key ordering across canvas, invites, records, ledger, tasks. |
| Dialogue delete/hide | `tests/test_workspace_generation_flow.py::test_delete_dialogue_hides_own_records_and_removes_dialogue` | Records are hidden and detached before dialogue delete. |
| Generation creation transaction | `huishi/routes_workspace.py` around `BEGIN IMMEDIATE`; broad workspace tests | Locks points, task creation, references, and billing state. Needs deeper P1 tests before PG migration. |
| Generation worker finalization | `tests/test_workspace_generation_flow.py::test_generation_worker_rolls_back_record_and_billing_when_success_mark_fails` | Record creation, billing, task success state, and generated output cleanup must commit or roll back together. |
| Billing deduction and ledger writes | `tests/test_generation_billing.py` | Points and ledger must stay atomic. |
| Invite redemption during registration | auth/invite tests are partial | Unique invitee constraint, reward ledger, and rollback behavior need P1 expansion. |
| Provider config save/delete | provider/settings tests | Encrypted keys and failover settings affect generation runtime. |
| Canvas conversations/messages | `tests/test_canvas_conversations.py` | Host session identity, message persistence, user isolation. |
| Bulk admin actions | partial admin tests | Dynamic `IN (...)` SQL and destructive user/package/invite operations. |

## Dynamic SQL Patterns

Dynamic `IN (...)` SQL now routes through `huishi.db.sql_placeholders(...)` in the covered settings, admin, and workspace paths. Conditional query string assembly remains in record listing and generation task listing, but it does not build variable-length `IN (...)` placeholder lists.

## Connection Boundary

Current rule:

- Production code may import `sqlite3` for SQLite exception types, but must not create direct connections outside `huishi/db.py`.
- `sqlite3.connect` must remain centralized in `huishi/db.py`.
- SQLite `PRAGMA` setup must remain centralized in `huishi/db.py`.
- Dynamic `IN (...)` placeholder creation should move toward `huishi.db.sql_placeholders(...)`.
- New multi-statement write flows should prefer `huishi.db.transaction()` once their existing commit/rollback behavior is covered by tests.
- SQLite write-lock flows should use `huishi.db.immediate_transaction()` instead of open-coded `BEGIN IMMEDIATE`.

Enforced by:

- `tests/test_database_access_boundary.py`
- `tests/test_db_helpers.py`

Current helper adoption:

- `huishi.routes_admin.delete_user_cascade(...)` uses `sql_placeholders(...)` for record-id `IN (...)` updates.
- `huishi.routes_admin.bulk_update_invites(...)` and `bulk_update_users(...)` use `sql_placeholders(...)` for selected-id `IN (...)` and `NOT IN (...)` queries.
- `huishi.providers.get_app_settings(...)` and `huishi.db.migrate_secret_values(...)` use `sql_placeholders(...)` for app-setting key `IN (...)` reads.
- `huishi.auth.register(...)` uses `transaction()` for the registration + invite redemption write boundary.
- `huishi.auth.reset_password_with_email_code(...)`, `verify_email(...)`, and `verify_email_link(...)` use `transaction()` for credential and verification-state updates.
- `huishi.routes_workspace.generate(...)` uses `immediate_transaction()` for generation task creation.
- `huishi.routes_workspace._finalize_generation(...)` uses `transaction()` for record creation plus billing deduction, with generated-upload cleanup after rollback.
- `huishi.generation_queue.run_generation_task(...)` wraps final record creation, billing, and success-state update in one `transaction()` and cleans generated outputs if finalization rolls back.
- `huishi.routes_workspace` bulk asset favorite, delete, and download paths use `sql_placeholders(...)` for record-id `IN (...)` queries.

## P1 Next Steps

1. Audit remaining multi-statement write flows and move covered paths to `transaction()` or `immediate_transaction()`.
2. Move schema/migration SQL toward a migration abstraction before PostgreSQL P2.
3. Keep all PostgreSQL conversion work out of P1 until this inventory and boundary are stable.
