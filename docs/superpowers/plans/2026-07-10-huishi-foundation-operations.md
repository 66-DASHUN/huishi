# Huishi Foundation and Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the running Huishi VM automated backups, verified production-secret evidence, least-privilege service definitions, complete canvas security headers, and a documented rollback path.

**Architecture:** Keep the current Flask/Next.js services. Add a Python PostgreSQL backup command that is testable without a database, systemd timer assets, deployment hardening, and response-header configuration. Root-only deployment steps remain explicit; application code never invokes `sudo`.

**Tech Stack:** Python 3.11+, pytest, PostgreSQL `pg_dump`/`pg_restore`, systemd, Nginx, Next.js 16, Bash deployment scripts.

---

### Task 1: Characterize and Verify Existing Production Secret Guards

**Files:**
- Test: `tests/test_sqlite_production_settings.py`
- Modify: `DEPLOY.md`

- [ ] **Step 1: Add characterization tests for all existing guards**

```python
from cryptography.fernet import Fernet


def test_production_rejects_default_session_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("HUISHI_ENV", "production")
    monkeypatch.setenv("HUISHI_SECRET_KEY", "dev-change-me")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    with pytest.raises(RuntimeError, match="HUISHI_SECRET_KEY"):
        create_app(testing=False)


def test_production_requires_encryption_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HUISHI_ENV", "production")
    monkeypatch.setenv("HUISHI_SECRET_KEY", "strong-session-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.delenv("HUISHI_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    with pytest.raises(RuntimeError, match="HUISHI_ENCRYPTION_KEY"):
        create_app(testing=False)


def test_production_rejects_default_admin_password(monkeypatch, tmp_path):
    monkeypatch.setenv("HUISHI_ENV", "production")
    monkeypatch.setenv("HUISHI_SECRET_KEY", "strong-session-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "1qaz@WSX")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    with pytest.raises(RuntimeError, match="HUISHI_ADMIN_PASSWORD"):
        create_app(testing=False)


def test_production_rejects_invalid_encryption_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HUISHI_ENV", "production")
    monkeypatch.setenv("HUISHI_SECRET_KEY", "strong-session-secret")
    monkeypatch.setenv("HUISHI_ADMIN_PASSWORD", "strong-admin-password")
    monkeypatch.setenv("HUISHI_ENCRYPTION_KEY", "not-a-fernet-key")
    monkeypatch.setenv("HUISHI_DATABASE", str(tmp_path / "prod.sqlite3"))
    with pytest.raises(RuntimeError, match="valid Fernet key"):
        create_app(testing=False)
```

- [ ] **Step 2: Run the characterization tests**

Run: `.venv/bin/python -m pytest -q tests/test_sqlite_production_settings.py -k 'production_rejects_default or production_requires_encryption or production_rejects_invalid'`

Expected: all selected tests pass against the existing `create_app()` production guards. No application code change is required.

- [ ] **Step 3: Record non-secret live configuration evidence after the first backup**

Run: `sudo -u huishi awk -F= '/^(HUISHI_ENV|HUISHI_SECRET_KEY|HUISHI_ADMIN_PASSWORD|HUISHI_ENCRYPTION_KEY)=/{print $1}' /opt/huishi/.env | sort`

Expected: exactly the four key names are printed and no values are printed. The running service is then restarted once; successful startup proves the existing runtime validation accepted their values.

- [ ] **Step 4: Document the guard and recovery requirement**

Document that losing `HUISHI_ENCRYPTION_KEY` makes encrypted Provider/User/SMTP secrets unreadable; the key must be stored in the encrypted operations backup separately from database dumps.

Expected: `DEPLOY.md` contains key rotation, backup, and restore consequences without including a real key.

### Task 2: Add Tested PostgreSQL Backups

**Files:**
- Create: `huishi/backup.py`
- Modify: `app.py`
- Create: `tests/test_backup.py`
- Modify: `deploy/env.vm-staging.example`

- [ ] **Step 1: Write failing tests for filename safety, retention, and command construction**

```python
def test_build_pg_dump_command_uses_custom_format(tmp_path):
    target = tmp_path / "huishi-20260710T120000Z.dump.part"
    command = build_pg_dump_command("postgresql://u:p@127.0.0.1/db", target)
    assert command == ["pg_dump", "--format=custom", "--no-owner", "--no-acl", f"--file={target}", "postgresql://u:p@127.0.0.1/db"]


def test_prune_backups_keeps_newest_files(tmp_path):
    paths = []
    for index in range(5):
        path = tmp_path / f"huishi-2026070{index + 1}T000000Z.dump"
        path.write_bytes(str(index).encode())
        paths.append(path)
    removed = prune_backups(tmp_path, keep=2)
    assert [path.name for path in removed] == [path.name for path in paths[:3]]
    assert paths[3].exists() and paths[4].exists()
```

- [ ] **Step 2: Verify backup tests fail because the module is missing**

Run: `.venv/bin/python -m pytest -q tests/test_backup.py`

Expected: collection fails with `ModuleNotFoundError: huishi.backup`.

- [ ] **Step 3: Implement atomic backup, checksum, status metadata, and retention**

```python
def create_backup(database_url: str, backup_dir: Path, keep: int, *, runner=subprocess.run, now=None) -> Path:
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    final_path = backup_dir / f"huishi-{stamp}.dump"
    partial_path = final_path.with_suffix(".dump.part")
    runner(build_pg_dump_command(database_url, partial_path), check=True, timeout=1800)
    if not partial_path.exists() or partial_path.stat().st_size == 0:
        raise RuntimeError("pg_dump produced an empty backup")
    partial_path.replace(final_path)
    digest = hashlib.sha256(final_path.read_bytes()).hexdigest()
    final_path.with_suffix(".dump.sha256").write_text(f"{digest}  {final_path.name}\n", encoding="ascii")
    write_status(backup_dir, ok=True, path=final_path, error="")
    prune_backups(backup_dir, keep=max(1, keep))
    return final_path
```

The module must expose `build_pg_dump_command`, `prune_backups`, `create_backup`, and `verify_backup`. `verify_backup` recomputes SHA-256 and raises on mismatch.

- [ ] **Step 4: Register a Flask CLI command**

```python
@app.cli.command("backup-postgres")
def backup_postgres_command() -> None:
    path = create_backup(
        app.config["DATABASE_URL"],
        Path(app.config["BACKUP_DIR"]),
        int(app.config["BACKUP_KEEP"]),
    )
    click.echo(path)
```

Add `HUISHI_BACKUP_DIR=/var/backups/huishi` and `HUISHI_BACKUP_KEEP=14` mappings to `Config` and the example environment file.

- [ ] **Step 5: Verify backup tests pass**

Run: `.venv/bin/python -m pytest -q tests/test_backup.py tests/test_sqlite_production_settings.py`

Expected: all selected tests pass.

### Task 3: Add Code Snapshots and Restore Instructions

**Files:**
- Create: `tools/code_snapshot.py`
- Create: `tests/test_code_snapshot.py`
- Modify: `DEPLOY.md`

- [ ] **Step 1: Write a failing exclusion test**

```python
def test_snapshot_excludes_secrets_and_runtime_data(tmp_path):
    project = tmp_path / "app"
    (project / "static/uploads").mkdir(parents=True)
    (project / ".env").write_text("SECRET=x", encoding="utf-8")
    (project / "app.py").write_text("print('ok')", encoding="utf-8")
    archive = create_snapshot(project, tmp_path / "backups", "test")
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "app/app.py" in names
    assert "app/.env" not in names
    assert not any("static/uploads" in name for name in names)
```

- [ ] **Step 2: Run the test and confirm the module is missing**

Run: `.venv/bin/python -m pytest -q tests/test_code_snapshot.py`

Expected: fail during import.

- [ ] **Step 3: Implement deterministic exclusions**

```python
EXCLUDED_PARTS = {".git", ".env", ".next", "node_modules", "__pycache__", ".pytest_cache", "uploads"}

def include_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return not any(part in EXCLUDED_PARTS for part in relative.parts)
```

Create the archive in a sibling backup directory, write a SHA-256 sidecar, and refuse an output path inside the source tree.

- [ ] **Step 4: Add exact restore and rollback commands to `DEPLOY.md`**

Document: verify checksum, stop services, unpack snapshot to a new release directory, restore a dump into a temporary database, run smoke, switch `/opt/huishi-current`, restart services, and retain the previous release until acceptance.

- [ ] **Step 5: Verify snapshot tests pass**

Run: `.venv/bin/python -m pytest -q tests/test_code_snapshot.py`

Expected: all tests pass and temporary archives contain no excluded paths.

### Task 4: Install Backup Units and Restrict Filesystem Permissions

**Files:**
- Create: `deploy/huishi-backup.service`
- Create: `deploy/huishi-backup.timer`
- Modify: `deploy/vm-staging-bootstrap.sh`
- Create: `deploy/huishi-canvas-agent.service`
- Test: `tests/test_deployment_assets.py`

- [ ] **Step 1: Write failing deployment-asset assertions**

```python
def test_backup_timer_is_persistent_and_daily():
    text = Path("deploy/huishi-backup.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 02:40:00" in text
    assert "Persistent=true" in text


def test_canvas_agent_uses_dedicated_home_and_systemd_sandbox():
    text = Path("deploy/huishi-canvas-agent.service").read_text(encoding="utf-8")
    assert "User=huishi-agent" in text
    assert "ProtectSystem=strict" in text
    assert "PrivateTmp=true" in text
    assert "NoNewPrivileges=true" in text
```

- [ ] **Step 2: Run the deployment tests and confirm missing assets fail**

Run: `.venv/bin/python -m pytest -q tests/test_deployment_assets.py`

Expected: fail because the backup unit and hardened agent service are absent.

- [ ] **Step 3: Add systemd units**

```ini
[Service]
Type=oneshot
User=huishi
Group=huishi
WorkingDirectory=/opt/huishi
EnvironmentFile=/opt/huishi/.env
ExecStart=/opt/huishi/.venv/bin/flask --app wsgi:app backup-postgres
PrivateTmp=true
NoNewPrivileges=true
```

The timer uses `OnCalendar=*-*-* 02:40:00`, `RandomizedDelaySec=10m`, and `Persistent=true`.

- [ ] **Step 4: Harden the Canvas Agent unit**

Use `User=huishi-agent`, `Group=huishi-agent`, `HOME=/var/lib/huishi-agent`, `PATH=/usr/local/bin:/usr/bin:/bin`, `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=true`, `PrivateDevices=true`, and a narrow `ReadWritePaths=/var/lib/huishi-agent`. The globally installed `/usr/local/bin/claude` and `/usr/local/bin/codex` remain read-only and executable.

Add a one-time root migration that copies only `.claude`, `.codex`, and `.infinite-canvas` from `/home/dashun` into `/var/lib/huishi-agent`, changes ownership to `huishi-agent:huishi-agent`, and sets directories to `700`. Never print or log credential file contents. Start the hardened service, then verify both Claude and Codex Agent modes before disabling the old service identity.

- [ ] **Step 5: Update bootstrap ownership**

The bootstrap creates `huishi-agent`, copies `deploy/huishi-canvas-agent.service` into `/etc/systemd/system`, uses root ownership for `/opt/huishi` after dependency install and build, grants read/execute to runtime accounts, and grants `huishi` write access only to `/var/lib/huishi`, `/var/log/huishi`, and `/var/backups/huishi`. Remove the final recursive `chown` of application code. Future releases build in a staging directory writable by the deploy account, then become root-owned before the active symlink switches.

- [ ] **Step 6: Verify deployment asset tests**

Run: `.venv/bin/python -m pytest -q tests/test_deployment_assets.py`

Expected: all tests pass.

### Task 5: Complete Canvas Security Headers and Graceful Stop

**Files:**
- Modify: `infinite-canvas/web/next.config.ts`
- Modify: `deploy/nginx-huishi.local.conf`
- Modify: `deploy/huishi-canvas.service`
- Test: `tests/test_deployment_assets.py`

- [ ] **Step 1: Add failing header and service assertions**

```python
def test_canvas_proxy_has_security_headers():
    text = Path("deploy/nginx-huishi.local.conf").read_text(encoding="utf-8")
    for header in ("X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"):
        assert header in text
    assert "proxy_hide_header X-Powered-By" in text


def test_canvas_service_accepts_sigterm_as_success():
    text = Path("deploy/huishi-canvas.service").read_text(encoding="utf-8")
    assert "SuccessExitStatus=143 SIGTERM" in text
```

- [ ] **Step 2: Verify the new assertions fail**

Run: `.venv/bin/python -m pytest -q tests/test_deployment_assets.py -k 'canvas_proxy or sigterm'`

Expected: both tests fail.

- [ ] **Step 3: Add headers at the Nginx boundary and disable framework disclosure**

```nginx
proxy_hide_header X-Powered-By;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

Set `poweredByHeader: false` in `next.config.ts`. Keep the existing dynamic `frame-ancestors` CSP.

- [ ] **Step 4: Mark expected stop signals as successful**

Add `SuccessExitStatus=143 SIGTERM` and `TimeoutStopSec=30` to `huishi-canvas.service`.

- [ ] **Step 5: Run focused verification**

Run: `.venv/bin/python -m pytest -q tests/test_deployment_assets.py`

Run: `cd infinite-canvas/web && bun run typecheck`

Expected: tests pass and TypeScript exits 0.

### Task 6: Stage, Deploy, Restore-Rehearse, and Smoke Test

**Files:**
- Modify: `DEPLOY.md`
- Create: `docs/product/runbooks/backup-restore.md`

- [ ] **Step 1: Run all foundation tests in an isolated test environment**

Run: `.venv/bin/python -m pytest -q tests/test_backup.py tests/test_code_snapshot.py tests/test_deployment_assets.py tests/test_sqlite_production_settings.py`

Expected: all selected tests pass without reading the production `.env`.

- [ ] **Step 2: Build the canvas in a temporary release directory**

Run: `cd infinite-canvas/web && bun run typecheck && bun run build`

Expected: both commands exit 0; do not overwrite the active `.next` until the build passes.

- [ ] **Step 3: Install root-owned units and permissions**

Run the documented root deployment command only after user approval. Validate with `systemd-analyze verify` and `nginx -t` before reload.

- [ ] **Step 4: Create and verify the first backup**

Run: `sudo -u huishi /opt/huishi/.venv/bin/flask --app wsgi:app backup-postgres`

Expected: one non-empty `.dump`, matching `.sha256`, and `status.json` with `ok: true`.

- [ ] **Step 5: Restore into an isolated rehearsal database**

Create `huishi_restore_rehearsal`, then run:

`pg_restore --clean --if-exists --no-owner --dbname=huishi_restore_rehearsal "$(/opt/huishi/.venv/bin/python -c 'import json; print(json.load(open("/var/backups/huishi/status.json", encoding="utf-8"))["path"])')"`

Run `tools/db_smoke.py` with `DATABASE_URL` set to the rehearsal database URL.

Expected: restore and smoke both exit 0; production database remains untouched.

- [ ] **Step 6: Verify online headers and services**

Run: `curl -k -I --resolve canvas.huishi.local:443:127.0.0.1 https://canvas.huishi.local/`

Expected: required headers exist and `X-Powered-By` is absent. `systemctl --failed` contains no Huishi unit.
