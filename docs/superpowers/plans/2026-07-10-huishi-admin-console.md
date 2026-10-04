# Huishi Admin Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing all-powerful admin pages into an auditable, searchable, permission-aware operations console with actionable health information.

**Architecture:** Add append-only audit storage, centralized permissions, read-only operations probes, and shared pagination helpers behind the existing Flask blueprint. Keep Jinja and the existing database boundary; progressively replace page-specific admin markup with a shared console shell.

**Tech Stack:** Flask 3, Jinja, PostgreSQL/SQLite compatibility layer, Redis/RQ, pytest, existing CSS/JavaScript.

---

### Task 1: Add the Append-Only Audit Schema

**Files:**
- Modify: `huishi/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_admin_audit.py`
- Modify: `docs/db/sql-inventory.md`

- [ ] **Step 1: Add isolated shared admin test fixtures**

```python
@pytest.fixture()
def app(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("HUISHI_OUTPUT_DIR", str(tmp_path / "uploads"))
    app = create_app(testing=True)
    with app.app_context():
        init_db()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login_admin(app):
    def login(client):
        with app.app_context():
            admin_id = get_db().execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()["id"]
        with client.session_transaction() as session:
            session["user_id"] = admin_id
        return int(admin_id)
    return login


@pytest.fixture()
def target_user_id(app):
    with app.app_context():
        cursor = get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, points, created_at) VALUES (?, ?, 'hash', 'user', 1, 20, 'now')",
            ("target@example.com", "target"),
        )
        get_db().commit()
        return int(cursor.lastrowid)
```

- [ ] **Step 2: Write a failing schema test**

```python
def test_admin_audit_table_is_initialized(app):
    with app.app_context():
        columns = get_db().execute("PRAGMA table_info(admin_audit_logs)").fetchall()
    assert [row["name"] for row in columns] == [
        "id", "actor_user_id", "action", "target_type", "target_id",
        "summary", "before_json", "after_json", "result", "request_id", "created_at",
    ]
```

- [ ] **Step 3: Verify the test fails because the table is absent**

Run: `.venv/bin/python -m pytest -q tests/test_admin_audit.py::test_admin_audit_table_is_initialized`

Expected: assertion fails with no columns.

- [ ] **Step 4: Add the portable schema**

```sql
CREATE TABLE IF NOT EXISTS admin_audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL DEFAULT '',
  target_id TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  before_json TEXT NOT NULL DEFAULT '{}',
  after_json TEXT NOT NULL DEFAULT '{}',
  result TEXT NOT NULL DEFAULT 'success',
  request_id TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor ON admin_audit_logs(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit_logs(action, created_at DESC);
```

- [ ] **Step 5: Verify SQLite and PostgreSQL schema translation**

Run: `.venv/bin/python -m pytest -q tests/test_admin_audit.py tests/test_db_backend.py`

Expected: both selected suites pass.

### Task 2: Implement Audit Redaction and Writes

**Files:**
- Create: `huishi/admin_audit.py`
- Modify: `tests/test_admin_audit.py`

- [ ] **Step 1: Write failing redaction and insert tests**

```python
def test_redact_audit_values_removes_secret_fields():
    assert redact_audit_values({"name": "primary", "api_key": "sk-secret", "smtp_password": "pw"}) == {
        "name": "primary", "api_key": "[redacted]", "smtp_password": "[redacted]",
    }


def test_record_admin_audit_stores_safe_json(app):
    with app.app_context():
        record_admin_audit(1, "provider.update", "provider", "7", before={"api_key": "old"}, after={"api_key": "new", "name": "primary"})
        get_db().commit()
        row = get_db().execute("SELECT * FROM admin_audit_logs").fetchone()
    assert json.loads(row["after_json"]) == {"api_key": "[redacted]", "name": "primary"}
```

- [ ] **Step 2: Verify tests fail because the module is absent**

Run: `.venv/bin/python -m pytest -q tests/test_admin_audit.py -k 'redact or stores_safe_json'`

Expected: import failure.

- [ ] **Step 3: Implement allowlisted serialization**

```python
SECRET_FIELDS = {"password", "password_hash", "api_key", "smtp_password", "canvas_agent_token", "token"}

def redact_audit_values(values: Mapping[str, object] | None) -> dict[str, object]:
    safe = {}
    for key, value in dict(values or {}).items():
        safe[key] = "[redacted]" if key.lower() in SECRET_FIELDS else value
    return safe


def record_admin_audit(actor_user_id, action, target_type="", target_id="", *, summary="", before=None, after=None, result="success", request_id=""):
    get_db().execute(
        """INSERT INTO admin_audit_logs
           (actor_user_id, action, target_type, target_id, summary, before_json, after_json, result, request_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (actor_user_id, action, target_type, str(target_id), summary,
         json.dumps(redact_audit_values(before), ensure_ascii=False, sort_keys=True),
         json.dumps(redact_audit_values(after), ensure_ascii=False, sort_keys=True),
         result, request_id, utc_now()),
    )
```

Add a Flask `before_request` hook that sets `g.request_id` to a validated incoming `X-Request-ID` or `secrets.token_hex(12)`, and an `after_request` hook that returns the same ID in the response header. `record_admin_audit` uses that value when no explicit request ID is supplied.

- [ ] **Step 4: Verify audit tests pass**

Run: `.venv/bin/python -m pytest -q tests/test_admin_audit.py`

Expected: all audit unit tests pass.

### Task 3: Audit Every High-Risk Admin Mutation

**Files:**
- Modify: `huishi/routes_admin.py`
- Modify: `huishi/routes_workspace.py`
- Modify: `tests/test_admin_audit.py`

- [ ] **Step 1: Add parameterized failing route tests**

```python
@pytest.mark.parametrize((suffix, data, action), [
    ("adjust", {"delta": "100", "admin_note": "support credit"}, "user.points.adjust"),
    ("password", {"password": "new-secret-123"}, "user.password.reset"),
    ("role", {"role": "support"}, "user.role.update"),
])
def test_admin_mutation_writes_audit(client, login_admin, target_user_id, suffix, data, action, app):
    login_admin(client)
    response = client.post(f"/admin/users/{target_user_id}/{suffix}", data=data)
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT * FROM admin_audit_logs WHERE action = ?", (action,)).fetchone()
    assert row is not None
    assert "new-secret-123" not in row["after_json"]
```

- [ ] **Step 2: Run the focused route tests and confirm no audit rows exist**

Run: `.venv/bin/python -m pytest -q tests/test_admin_audit.py -k mutation`

Expected: all parameterized cases fail on `row is not None`.

- [ ] **Step 3: Add audit writes in the same transaction as each successful mutation**

For every mutation, capture only safe fields before the update, execute the update, call `record_admin_audit(...)`, then commit once. Cover user adjust/reset/role/delete/import/bulk, invites, packages, pricing, Provider changes, SMTP, canvas and Agent settings.

```python
record_admin_audit(
    g.user["id"], "user.points.adjust", "user", user_id,
    summary=note.strip(), before={"points": int(user["points"])},
    after={"points": int(user["points"]) + delta, "delta": delta},
    request_id=g.request_id,
)
```

- [ ] **Step 4: Record rejected high-risk attempts without leaking submitted secrets**

Use a separate `record_failed_admin_audit(...)` helper after rolling back, with `result="rejected"`, a safe error code, and no submitted password/key/token fields.

- [ ] **Step 5: Verify route and transaction tests**

Run: `.venv/bin/python -m pytest -q tests/test_admin_audit.py tests/test_admin_delete_user_cascade.py tests/test_provider_scheduling.py tests/test_settings_config_status.py`

Expected: all selected tests pass.

### Task 4: Centralize Role Permissions

**Files:**
- Create: `huishi/admin_permissions.py`
- Modify: `huishi/auth.py`
- Modify: `huishi/routes_admin.py`
- Create: `tests/test_admin_permissions.py`

- [ ] **Step 1: Write a failing permission matrix test**

```python
@pytest.mark.parametrize((role, permission, allowed), [
    ("admin", "users.delete", True),
    ("super_admin", "users.delete", True),
    ("operator", "providers.update", True),
    ("operator", "users.delete", False),
    ("support", "users.points.adjust", True),
    ("support", "users.role.update", False),
    ("viewer", "audit.view", True),
    ("viewer", "users.points.adjust", False),
    ("user", "admin.view", False),
])
def test_permission_matrix(role, permission, allowed):
    assert has_permission(role, permission) is allowed
```

- [ ] **Step 2: Verify permission tests fail on missing module**

Run: `.venv/bin/python -m pytest -q tests/test_admin_permissions.py`

Expected: import failure.

- [ ] **Step 3: Implement immutable permission sets**

```python
ROLE_PERMISSIONS = {
    "admin": frozenset({"*"}),
    "super_admin": frozenset({"*"}),
    "operator": frozenset({"admin.view", "operations.view", "providers.view", "providers.update", "records.view"}),
    "support": frozenset({"admin.view", "users.view", "users.points.adjust", "users.login_failures.reset", "records.view"}),
    "viewer": frozenset({"admin.view", "operations.view", "users.view", "records.view", "audit.view"}),
    "user": frozenset(),
}

def has_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, frozenset())
    return "*" in permissions or permission in permissions
```

- [ ] **Step 4: Add `permission_required` and route annotations**

Keep `admin_required` as a compatibility wrapper for `admin.view`. Apply explicit permissions to every management route. Return 403 for authenticated users without permission and the existing login surface for anonymous users.

Expand role validation in the role-update and CSV-import paths to the shared role set. Only `super_admin` and legacy `admin` may grant or revoke management roles; CSV import defaults to `user` and cannot create management roles unless the actor has `users.role.update`.

- [ ] **Step 5: Verify route allow/deny behavior**

Run: `.venv/bin/python -m pytest -q tests/test_admin_permissions.py tests/test_auth_transactions.py`

Expected: all role matrix and route tests pass.

### Task 5: Add Operations Health Collection

**Files:**
- Create: `huishi/operations.py`
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/dashboard.html`
- Create: `tests/test_operations_health.py`

- [ ] **Step 1: Write failing degraded-dependency tests**

```python
def test_collect_operations_health_isolates_probe_failures(monkeypatch, app):
    monkeypatch.setattr("huishi.operations.probe_redis", lambda *_: (_ for _ in ()).throw(TimeoutError("slow")))
    monkeypatch.setattr("huishi.operations.probe_canvas", lambda *_: {"status": "ok", "latency_ms": 12})
    with app.app_context():
        health = collect_operations_health()
    assert health["redis"]["status"] == "error"
    assert health["canvas"]["status"] == "ok"
```

- [ ] **Step 2: Verify the test fails because the collector is missing**

Run: `.venv/bin/python -m pytest -q tests/test_operations_health.py`

Expected: import failure.

- [ ] **Step 3: Implement short, isolated probes**

Collect database `SELECT 1`, Redis ping and RQ queue/worker counts, canvas HTTP status, Agent HTTP status, `shutil.disk_usage`, latest backup `status.json`, generation failures in the last 24 hours, and last storage sweep journal metadata. Every probe returns `{status, message, checked_at}` and catches its own exceptions.

- [ ] **Step 4: Render actionable status without blocking the page**

Add status rows for database, Redis/queue, canvas, Agent, disk, backup, failed tasks, and storage cleanup. Use cards only for the three top metrics; render the rest as a scan-friendly table.

- [ ] **Step 5: Verify collector and dashboard tests**

Run: `.venv/bin/python -m pytest -q tests/test_operations_health.py tests/test_account_experience.py`

Expected: all selected tests pass.

### Task 6: Add Shared Server-Side Pagination and Filters

**Files:**
- Create: `huishi/pagination.py`
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/users.html`
- Modify: `templates/admin/invites.html`
- Modify: `templates/admin/records.html`
- Modify: `templates/admin/user_ledger.html`
- Create: `templates/admin/_pagination.html`
- Create: `tests/test_admin_pagination.py`

- [ ] **Step 1: Write failing normalization and route tests**

```python
def test_page_query_clamps_values():
    assert PageQuery.from_values("0", "500").page == 1
    assert PageQuery.from_values("0", "500").per_page == 100


def test_users_page_filters_by_search(client, login_admin, target_user_id, app):
    with app.app_context():
        get_db().execute(
            "INSERT INTO users (email, username, password_hash, role, email_verified, points, created_at) VALUES ('other@example.com', 'other', 'hash', 'user', 1, 0, 'now')"
        )
        get_db().commit()
    login_admin(client)
    response = client.get("/admin/users?q=target&page=1&per_page=20")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "target@example.com" in body
    assert "other@example.com" not in body
```

- [ ] **Step 2: Verify pagination tests fail**

Run: `.venv/bin/python -m pytest -q tests/test_admin_pagination.py`

Expected: missing module or unfiltered output failures.

- [ ] **Step 3: Implement normalized pagination**

```python
@dataclass(frozen=True)
class PageQuery:
    page: int
    per_page: int

    @classmethod
    def from_values(cls, page, per_page):
        return cls(max(1, parse_int(page, 1)), min(100, max(10, parse_int(per_page, 20))))

    @property
    def offset(self):
        return (self.page - 1) * self.per_page
```

- [ ] **Step 4: Replace full-table reads with count plus page queries**

Use bound parameters for search values, status, role, action, and date range. Keep sort columns allowlisted; never interpolate raw query parameters into SQL.

- [ ] **Step 5: Render shared pagination and preserved filters**

The partial shows total count, current page, previous/next, and retains all filters using `url_for` query arguments.

- [ ] **Step 6: Verify pagination and existing admin tests**

Run: `.venv/bin/python -m pytest -q tests/test_admin_pagination.py tests/test_admin_delete_user_cascade.py tests/test_package_defaults.py`

Expected: all selected tests pass.

### Task 7: Build the Operations Console Shell and Audit Page

**Files:**
- Modify: `templates/admin/layout.html`
- Create: `templates/admin/audit.html`
- Modify: `templates/admin/dashboard.html`
- Modify: `templates/admin/users.html`
- Modify: `static/css/site.css`
- Modify: `static/js/admin.js`
- Modify: `huishi/routes_admin.py`
- Test: `tests/test_admin_console_experience.py`

- [ ] **Step 1: Write failing semantic UI tests**

```python
def test_admin_layout_has_primary_navigation_and_current_page(client, login_admin):
    login_admin(client)
    body = client.get("/admin/audit").get_data(as_text=True)
    assert 'aria-label="管理导航"' in body
    assert 'aria-current="page"' in body
    assert 'name="q"' in body
    assert "审计日志" in body
```

- [ ] **Step 2: Verify the audit route and shell tests fail**

Run: `.venv/bin/python -m pytest -q tests/test_admin_console_experience.py`

Expected: 404 for `/admin/audit` or missing semantic elements.

- [ ] **Step 3: Implement the shared shell**

Use a left navigation for dashboard, users, tasks/records, billing, invites, configuration, and audit. Show permitted entries only, mark the current page with `aria-current="page"`, and retain a direct return to the workspace.

- [ ] **Step 4: Implement audit search and detail drawer**

Support `q`, `action`, `result`, `actor`, `from`, `to`, and pagination. Render a compact table; opening a row shows safe before/after JSON in the existing drawer pattern.

- [ ] **Step 5: Fix drawer keyboard behavior**

Add Escape-to-close, initial focus, focus restoration, and a click-outside backdrop. Delete actions remain native forms and use explicit confirmation text naming the target.

- [ ] **Step 6: Verify UI contract tests and JavaScript syntax**

Run: `.venv/bin/python -m pytest -q tests/test_admin_console_experience.py tests/test_admin_pagination.py tests/test_admin_audit.py`

Run: `node --check static/js/admin.js`

Expected: tests pass and JavaScript syntax exits 0.

### Task 8: Verify and Deploy the Admin Console

**Files:**
- Modify: `docs/product/confirmed-requirements.md`
- Create: `docs/product/runbooks/admin-console.md`

- [ ] **Step 1: Run isolated backend regression**

Run: `env -u DATABASE_URL -u HUISHI_TEST_DATABASE_URL -u HUISHI_REQUIRE_POSTGRES -u HUISHI_TEST_REQUIRE_POSTGRES HUISHI_ENV=test HUISHI_DATABASE=/tmp/huishi-pytest.sqlite3 HUISHI_OUTPUT_DIR=/tmp/huishi-pytest-uploads .venv/bin/python -m pytest -q`

Expected: all tests pass; no connection is made to the production PostgreSQL URL.

- [ ] **Step 2: Run a PostgreSQL test profile against a dedicated test database**

Run: `HUISHI_ENV=test HUISHI_TEST_DATABASE_URL="$HUISHI_TEST_DATABASE_URL" HUISHI_TEST_REQUIRE_POSTGRES=1 HUISHI_OUTPUT_DIR=/tmp/huishi-pg-test-uploads .venv/bin/python -m pytest -q tests/test_admin_audit.py tests/test_admin_permissions.py tests/test_admin_pagination.py tests/test_operations_health.py`

Expected: schema, audit writes, permissions, pagination, and health tests pass against a database URL reserved for tests; the command refuses to run when `HUISHI_TEST_DATABASE_URL` is unset or equals the production URL.

- [ ] **Step 3: Create a pre-deploy database backup and code snapshot**

Verify both checksums before changing active files.

- [ ] **Step 4: Deploy additively and smoke test each role**

Verify dashboard, user search, audit search, permission denials, point adjustment, Provider diagnostics, and logout. Use dedicated test accounts; do not change real user data.

- [ ] **Step 5: Perform desktop and mobile visual QA**

Check 1440x900, 1280x720, 768x1024, and 390x844 for clipping, table fallback, drawer focus, dangerous-action separation, empty/error states, and readable contrast.
