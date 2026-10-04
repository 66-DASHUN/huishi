# Canvas Identity Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让主站成为画布的唯一身份源，由主站签发短时 `canvas session token`，画布在进入项目列表页和编辑页前完成校验并拿到 `user_id / role / billing_identity`，为后续统一计费、资产回流和运行控制打下基础。

**Architecture:** Flask 主站新增独立的画布会话签发与校验模块，`/canvas` 页面继续保留 iframe 承载，但在 iframe URL 上携带短时 host session bootstrap 参数。Next.js 画布新增 host session guard，在项目列表页与项目编辑页启动前先向主站校验 token，校验成功后把身份写入专用 store，校验失败则停留在未授权态，不进入现有画布交互逻辑。

**Tech Stack:** Flask、Jinja2、SQLite、itsdangerous、pytest、Next.js 16、React 19、TypeScript、Zustand

---

## 文件结构与职责

- `D:/AI/huishihuabu/huishi/canvas_session.py`
  - 新增主站侧画布会话签发与验签逻辑。
  - 统一定义 payload 结构、TTL、错误类型、`billing_identity` 生成规则。
- `D:/AI/huishihuabu/huishi/routes_workspace.py`
  - 让 `/canvas` 生成带 bootstrap 参数的 iframe URL。
  - 新增 `POST /api/canvas/session/verify` 供画布跨域校验 token。
  - 为校验接口补最小 CORS 头，只允许已配置的画布 origin。
- `D:/AI/huishihuabu/huishi/config.py`
  - 新增 `CANVAS_SESSION_TTL_SECONDS` 配置项。
- `D:/AI/huishihuabu/templates/canvas.html`
  - 保留现有资产桥接逻辑。
  - 使用主站生成的 `canvas_embed_url`，不再只拼裸 `/canvas`。
- `D:/AI/huishihuabu/tests/test_canvas_identity_session.py`
  - 新增主站侧会话签发、TTL、校验接口、CORS 行为测试。
- `D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`
  - 补 `/canvas` 页面 bootstrap 回归测试，保护现有 iframe 和资产桥接。
- `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/lib/host-canvas-session.ts`
  - 新增画布侧读取 query bootstrap 参数、请求主站校验接口、标准化返回结构的 helper。
- `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/stores/use-canvas-host-session-store.ts`
  - 新增画布身份 store，保存 `authenticated / loading / userId / role / billingIdentity / expiresAt / verifyUrl`。
- `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/components/canvas-host-session-guard.tsx`
  - 新增统一身份守卫组件，负责 loading / unauthorized / success 三态。
- `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/page.tsx`
  - 项目列表页接入 host session guard。
- `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/[id]/page.tsx`
  - 项目编辑页接入 host session guard。
- `D:/AI/huishihuabu/tests/test_canvas_identity_phase1_external.py`
  - 用源码断言保护画布项目的 guard 接入点和身份 store 字段，避免这个阶段没有 TS 测试框架时完全失守。

---

### Task 1: 新增主站侧画布会话签发模块

**Files:**
- Create: `D:/AI/huishihuabu/huishi/canvas_session.py`
- Modify: `D:/AI/huishihuabu/huishi/config.py`
- Test: `D:/AI/huishihuabu/tests/test_canvas_identity_session.py`

- [ ] **Step 1: 先写失败测试，锁定 token payload、TTL 和过期行为**

```python
from pathlib import Path

import pytest

from app import create_app
from huishi.db import get_db, init_db


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(testing=True)
    app.config["DATABASE"] = tmp_path / "test.sqlite3"
    app.config["OUTPUT_DIR"] = tmp_path / "uploads"
    app.config["CANVAS_SESSION_TTL_SECONDS"] = 600
    with app.app_context():
        init_db()
    return app


def create_user(role: str = "user", username: str = "canvas-user") -> int:
    cursor = get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, email_verified, points, created_at)
        VALUES (?, '', 'hash', ?, 1, 20, 'now')
        """,
        (username, role),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def test_issue_canvas_session_token_contains_identity_fields(app):
    from huishi.canvas_session import issue_canvas_session_token, verify_canvas_session_token

    with app.app_context():
        user_id = create_user(role="admin", username="root")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        token, expires_at = issue_canvas_session_token(user)
        payload = verify_canvas_session_token(token)

    assert token
    assert expires_at > 0
    assert payload["user_id"] == user_id
    assert payload["username"] == "root"
    assert payload["role"] == "admin"
    assert payload["billing_identity"] == f"user:{user_id}"
    assert "issued_at" in payload
    assert "expires_at" in payload


def test_verify_canvas_session_token_rejects_expired_token(app, monkeypatch):
    from huishi.canvas_session import CanvasSessionError, issue_canvas_session_token, verify_canvas_session_token

    with app.app_context():
        user_id = create_user()
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)

        monkeypatch.setattr("huishi.canvas_session.time.time", lambda: 10**10)

        with pytest.raises(CanvasSessionError) as exc:
            verify_canvas_session_token(token)

    assert str(exc.value) == "expired"
```

- [ ] **Step 2: 运行测试，确认它们先失败**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_session.py::test_issue_canvas_session_token_contains_identity_fields D:\AI\huishihuabu\tests\test_canvas_identity_session.py::test_verify_canvas_session_token_rejects_expired_token -v
```

Expected:

- 失败，原因是 `huishi.canvas_session` 还不存在。

- [ ] **Step 3: 编写最小实现，集中定义 token 签发与验签**

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


CANVAS_SESSION_SALT = "huishi.canvas.session"


@dataclass(slots=True)
class CanvasSessionError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


def canvas_session_ttl_seconds() -> int:
    return int(current_app.config.get("CANVAS_SESSION_TTL_SECONDS", 600))


def canvas_billing_identity(user_id: int) -> str:
    return f"user:{int(user_id)}"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(current_app.config["SECRET_KEY"]), salt=CANVAS_SESSION_SALT)


def issue_canvas_session_token(user) -> tuple[str, int]:
    now = int(time.time())
    ttl = canvas_session_ttl_seconds()
    payload = {
        "user_id": int(user["id"]),
        "username": str(user["username"] or ""),
        "role": str(user["role"] or "user"),
        "billing_identity": canvas_billing_identity(int(user["id"])),
        "issued_at": now,
        "expires_at": now + ttl,
    }
    return _serializer().dumps(payload), payload["expires_at"]


def verify_canvas_session_token(token: str) -> dict[str, Any]:
    if not token.strip():
        raise CanvasSessionError("missing")
    try:
        payload = _serializer().loads(token, max_age=canvas_session_ttl_seconds())
    except SignatureExpired as exc:
        raise CanvasSessionError("expired") from exc
    except BadSignature as exc:
        raise CanvasSessionError("invalid") from exc

    required = {"user_id", "username", "role", "billing_identity", "issued_at", "expires_at"}
    if not required.issubset(payload):
        raise CanvasSessionError("invalid")
    if str(payload["role"]) not in {"user", "admin"}:
        raise CanvasSessionError("invalid")
    if int(payload["expires_at"]) < int(time.time()):
        raise CanvasSessionError("expired")
    return payload
```

```python
# D:/AI/huishihuabu/huishi/config.py
class Config:
    CANVAS_SESSION_TTL_SECONDS = int(os.environ.get("HUISHI_CANVAS_SESSION_TTL_SECONDS", "600"))
```

- [ ] **Step 4: 重新运行测试，确认签发与过期逻辑通过**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_session.py::test_issue_canvas_session_token_contains_identity_fields D:\AI\huishihuabu\tests\test_canvas_identity_session.py::test_verify_canvas_session_token_rejects_expired_token -v
```

Expected:

- 2 passed

- [ ] **Step 5: 记录检查点**

```powershell
git rev-parse --is-inside-work-tree
git add D:\AI\huishihuabu\huishi\canvas_session.py D:\AI\huishihuabu\huishi\config.py D:\AI\huishihuabu\tests\test_canvas_identity_session.py
git commit -m "feat: add canvas session token primitives"
```

Expected:

- 如果当前目录是 git 仓库，提交成功。
- 如果不是 git 仓库，保留“测试已通过”的检查点，不做额外文件变更。

---

### Task 2: 主站输出 iframe bootstrap，并提供画布校验接口

**Files:**
- Modify: `D:/AI/huishihuabu/huishi/routes_workspace.py`
- Modify: `D:/AI/huishihuabu/templates/canvas.html`
- Test: `D:/AI/huishihuabu/tests/test_canvas_identity_session.py`
- Test: `D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **Step 1: 先写失败测试，锁定 `/canvas` bootstrap 和 `/api/canvas/session/verify` 行为**

```python
def login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def test_canvas_verify_endpoint_returns_live_user_context(app):
    from huishi.canvas_session import issue_canvas_session_token
    from huishi.providers import save_canvas_setting

    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user(role="admin", username="captain")
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token, _ = issue_canvas_session_token(user)
        get_db().commit()

    with app.test_client() as client:
        response = client.post(
            "/api/canvas/session/verify",
            json={"token": token},
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["authenticated"] is True
    assert payload["user"]["id"] == user_id
    assert payload["user"]["role"] == "admin"
    assert payload["billing_identity"] == f"user:{user_id}"
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"


def test_canvas_page_embeds_host_session_bootstrap(app):
    from huishi.providers import save_canvas_setting

    app.config["CANVAS_APP_URL"] = "http://127.0.0.1:3000"
    with app.app_context():
        save_canvas_setting("canvas_app_url", "http://127.0.0.1:3000")
        user_id = create_user()
        get_db().commit()

    with app.test_client() as client:
        login(client, user_id)
        response = client.get("/canvas")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "host_mode=huishi" in html
    assert "host_session_token=" in html
    assert "host_session_verify_url=" in html
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_session.py::test_canvas_verify_endpoint_returns_live_user_context D:\AI\huishihuabu\tests\test_workspace_generation_flow.py::test_canvas_page_embeds_host_session_bootstrap -v
```

Expected:

- 失败，原因是校验接口还不存在，`/canvas` 也还没有携带 host session bootstrap。

- [ ] **Step 3: 在主站 `/canvas` 页面为 iframe 生成带 token 的嵌入地址**

```python
from urllib.parse import urlencode, urlsplit

from huishi.canvas_session import issue_canvas_session_token, canvas_billing_identity, verify_canvas_session_token, CanvasSessionError


def _configured_canvas_origin(canvas_app_url: str) -> str:
    parsed = urlsplit(canvas_app_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_canvas_embed_url(canvas_app_url: str, token: str) -> str:
    base_url = canvas_app_url.rstrip("/")
    verify_url = url_for("workspace.canvas_session_verify", _external=True)
    query = urlencode(
        {
            "host_mode": "huishi",
            "host_session_token": token,
            "host_session_verify_url": verify_url,
            "host_origin": request.host_url.rstrip("/"),
        }
    )
    return f"{base_url}/canvas?{query}"


@bp.get("/canvas")
@login_required
def canvas():
    canvas_settings = provider_store.get_canvas_settings()
    canvas_app_url = str(canvas_settings.get("canvas_app_url") or current_app.config.get("CANVAS_APP_URL") or "").strip().rstrip("/")
    canvas_token, _ = issue_canvas_session_token(g.user)
    canvas_embed_url = _build_canvas_embed_url(canvas_app_url, canvas_token) if canvas_app_url else ""
    return render_template(
        "canvas.html",
        canvas_settings=canvas_settings,
        canvas_app_url=canvas_app_url,
        canvas_embed_url=canvas_embed_url,
        active_dialogue=last_workspace_dialogue_for_user(g.user["id"]),
    )
```

- [ ] **Step 4: 新增主站校验接口和最小 CORS 头**

```python
from flask import Response


def _add_canvas_cors(response: Response, canvas_origin: str) -> Response:
    request_origin = request.headers.get("Origin", "")
    if canvas_origin and request_origin == canvas_origin:
        response.headers["Access-Control-Allow-Origin"] = canvas_origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


@bp.route("/api/canvas/session/verify", methods=("POST", "OPTIONS"))
def canvas_session_verify():
    canvas_settings = provider_store.get_canvas_settings()
    canvas_app_url = str(canvas_settings.get("canvas_app_url") or current_app.config.get("CANVAS_APP_URL") or "").strip()
    canvas_origin = _configured_canvas_origin(canvas_app_url)

    if request.method == "OPTIONS":
        return _add_canvas_cors(current_app.response_class("", status=204), canvas_origin)

    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token") or "").strip()
    try:
        claims = verify_canvas_session_token(token)
    except CanvasSessionError as exc:
        response = jsonify({"authenticated": False, "reason": str(exc)})
        response.status_code = 401
        return _add_canvas_cors(response, canvas_origin)

    user = get_db().execute(
        "SELECT id, username, role, points FROM users WHERE id = ?",
        (int(claims["user_id"]),),
    ).fetchone()
    if user is None:
        response = jsonify({"authenticated": False, "reason": "user_not_found"})
        response.status_code = 404
        return _add_canvas_cors(response, canvas_origin)

    response = jsonify(
        {
            "authenticated": True,
            "user": {
                "id": int(user["id"]),
                "username": str(user["username"] or ""),
                "role": str(user["role"] or "user"),
                "points": int(user["points"] or 0),
            },
            "billing_identity": canvas_billing_identity(int(user["id"])),
            "expires_at": int(claims["expires_at"]),
        }
    )
    return _add_canvas_cors(response, canvas_origin)
```

- [ ] **Step 5: 保持 `templates/canvas.html` 只承载，不改动现有桥接协议**

```html
{% if canvas_embed_url %}
  <section class="canvas-frame-wrap">
    <iframe class="canvas-frame" src="{{ canvas_embed_url }}" title="画布" loading="lazy"></iframe>
  </section>
{% else %}
  <section class="canvas-empty-state">
    <h2>未配置画布地址</h2>
    <p>请先在管理页面填写画布应用地址，然后这里会嵌入完整画布应用。</p>
  </section>
{% endif %}

<script>
  (() => {
    const bridgeKey = "huishi.canvas.bridge";
    const frame = document.querySelector(".canvas-frame");
    const raw = sessionStorage.getItem(bridgeKey);
    if (!raw || !frame) return;
    try {
      const payload = JSON.parse(raw);
      const send = () => {
        if (!frame.contentWindow) return false;
        frame.contentWindow.postMessage({ type: "huishi-canvas-import", payload }, "*");
        sessionStorage.removeItem(bridgeKey);
        window.removeEventListener("message", handleReady);
        return true;
      };
      const handleReady = (event) => {
        if (event.source !== frame.contentWindow) return;
        if ((event.data || {}).type !== "huishi-canvas-ready") return;
        send();
      };
      window.addEventListener("message", handleReady);
      frame.addEventListener(
        "load",
        () => {
          if (frame.contentWindow) frame.contentWindow.postMessage({ type: "huishi-canvas-ping" }, "*");
        },
        { once: true }
      );
    } catch {
      sessionStorage.removeItem(bridgeKey);
    }
  })();
</script>
```

- [ ] **Step 6: 重新运行测试，确认主站 bootstrap 与校验接口通过**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_session.py::test_canvas_verify_endpoint_returns_live_user_context D:\AI\huishihuabu\tests\test_workspace_generation_flow.py::test_canvas_page_embeds_host_session_bootstrap -v
```

Expected:

- 2 passed

- [ ] **Step 7: 记录检查点**

```powershell
git rev-parse --is-inside-work-tree
git add D:\AI\huishihuabu\huishi\routes_workspace.py D:\AI\huishihuabu\templates\canvas.html D:\AI\huishihuabu\tests\test_canvas_identity_session.py D:\AI\huishihuabu\tests\test_workspace_generation_flow.py
git commit -m "feat: expose canvas host session bootstrap and verify api"
```

---

### Task 3: 在画布项目新增 host session helper 和身份 store

**Files:**
- Create: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/lib/host-canvas-session.ts`
- Create: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/stores/use-canvas-host-session-store.ts`
- Test: `D:/AI/huishihuabu/tests/test_canvas_identity_phase1_external.py`

- [ ] **Step 1: 先写失败测试，用源码断言保护 helper 与 store 的关键字段**

```python
from pathlib import Path


CANVAS_ROOT = Path(r"D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas")


def test_canvas_host_session_helper_defines_verify_contract():
    source = (CANVAS_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")

    assert "export type HostCanvasSessionPayload" in source
    assert "host_session_token" in source
    assert "host_session_verify_url" in source
    assert "verifyHostCanvasSession" in source


def test_canvas_host_session_store_exposes_billing_identity():
    source = (CANVAS_ROOT / "stores/use-canvas-host-session-store.ts").read_text(encoding="utf-8")

    assert "billingIdentity" in source
    assert "authenticated" in source
    assert "expiresAt" in source
    assert "setSession" in source
    assert "clearSession" in source
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_host_session_helper_defines_verify_contract D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_host_session_store_exposes_billing_identity -v
```

Expected:

- 失败，原因是 helper 和 store 文件尚不存在。

- [ ] **Step 3: 新增画布侧 bootstrap helper，统一读取 query 和请求主站校验**

```ts
export type HostCanvasSessionBootstrap = {
    mode: string;
    token: string;
    verifyUrl: string;
    hostOrigin: string;
};

export type HostCanvasSessionPayload = {
    authenticated: boolean;
    user?: {
        id: number;
        username: string;
        role: "user" | "admin";
        points: number;
    };
    billing_identity?: string;
    expires_at?: number;
    reason?: string;
};

export function readHostCanvasBootstrap(search: URLSearchParams): HostCanvasSessionBootstrap | null {
    const mode = search.get("host_mode") || "";
    const token = search.get("host_session_token") || "";
    const verifyUrl = search.get("host_session_verify_url") || "";
    const hostOrigin = search.get("host_origin") || "";
    if (mode !== "huishi" || !token || !verifyUrl) return null;
    return { mode, token, verifyUrl, hostOrigin };
}

export async function verifyHostCanvasSession(bootstrap: HostCanvasSessionBootstrap): Promise<HostCanvasSessionPayload> {
    const response = await fetch(bootstrap.verifyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: bootstrap.token }),
        cache: "no-store",
    });
    const payload = (await response.json()) as HostCanvasSessionPayload;
    if (!response.ok) return { ...payload, authenticated: false };
    return payload;
}
```

- [ ] **Step 4: 新增身份 store，作为后续计费和权限绑定的唯一画布上下文**

```ts
import { create } from "zustand";

type CanvasHostSessionState = {
    loading: boolean;
    authenticated: boolean;
    userId: number | null;
    username: string;
    role: "user" | "admin" | "";
    billingIdentity: string;
    expiresAt: number | null;
    verifyUrl: string;
    setLoading: (loading: boolean) => void;
    setSession: (payload: {
        userId: number;
        username: string;
        role: "user" | "admin";
        billingIdentity: string;
        expiresAt: number | null;
        verifyUrl: string;
    }) => void;
    clearSession: () => void;
};

export const useCanvasHostSessionStore = create<CanvasHostSessionState>((set) => ({
    loading: true,
    authenticated: false,
    userId: null,
    username: "",
    role: "",
    billingIdentity: "",
    expiresAt: null,
    verifyUrl: "",
    setLoading: (loading) => set({ loading }),
    setSession: (payload) =>
        set({
            loading: false,
            authenticated: true,
            userId: payload.userId,
            username: payload.username,
            role: payload.role,
            billingIdentity: payload.billingIdentity,
            expiresAt: payload.expiresAt,
            verifyUrl: payload.verifyUrl,
        }),
    clearSession: () =>
        set({
            loading: false,
            authenticated: false,
            userId: null,
            username: "",
            role: "",
            billingIdentity: "",
            expiresAt: null,
            verifyUrl: "",
        }),
}));
```

- [ ] **Step 5: 重新运行测试，确认 helper 和 store 已落地**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_host_session_helper_defines_verify_contract D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_host_session_store_exposes_billing_identity -v
```

Expected:

- 2 passed

- [ ] **Step 6: 记录检查点**

```powershell
git rev-parse --is-inside-work-tree
git add D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\lib\host-canvas-session.ts D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\stores\use-canvas-host-session-store.ts D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py
git commit -m "feat: add canvas host session helper and store"
```

---

### Task 4: 给画布项目列表页和编辑页接入统一身份守卫

**Files:**
- Create: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/components/canvas-host-session-guard.tsx`
- Modify: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/page.tsx`
- Modify: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/[id]/page.tsx`
- Test: `D:/AI/huishihuabu/tests/test_canvas_identity_phase1_external.py`

- [ ] **Step 1: 先写失败测试，锁定两个入口页都必须经过 guard**

```python
def test_canvas_host_session_guard_has_loading_and_unauthorized_states():
    source = (CANVAS_ROOT / "components/canvas-host-session-guard.tsx").read_text(encoding="utf-8")

    assert "会话校验中" in source
    assert "未授权" in source
    assert "verifyHostCanvasSession" in source
    assert "useCanvasHostSessionStore" in source


def test_canvas_pages_are_wrapped_by_host_session_guard():
    page_source = (CANVAS_ROOT / "page.tsx").read_text(encoding="utf-8")
    detail_source = (CANVAS_ROOT / "[id]/page.tsx").read_text(encoding="utf-8")

    assert "CanvasHostSessionGuard" in page_source
    assert "CanvasHostSessionGuard" in detail_source
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_host_session_guard_has_loading_and_unauthorized_states D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_pages_are_wrapped_by_host_session_guard -v
```

Expected:

- 失败，原因是 guard 还不存在，两个页面也还没包裹。

- [ ] **Step 3: 新增统一 guard 组件，先校验再放行**

```tsx
"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

import { readHostCanvasBootstrap, verifyHostCanvasSession } from "../lib/host-canvas-session";
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";

export function CanvasHostSessionGuard({ children }: { children: React.ReactNode }) {
    const searchParams = useSearchParams();
    const { loading, authenticated, setLoading, setSession, clearSession } = useCanvasHostSessionStore();

    useEffect(() => {
        let active = true;
        const bootstrap = readHostCanvasBootstrap(searchParams);
        if (!bootstrap) {
            clearSession();
            return;
        }

        setLoading(true);
        void verifyHostCanvasSession(bootstrap)
            .then((payload) => {
                if (!active || !payload.authenticated || !payload.user) {
                    clearSession();
                    return;
                }
                setSession({
                    userId: payload.user.id,
                    username: payload.user.username,
                    role: payload.user.role,
                    billingIdentity: payload.billing_identity || `user:${payload.user.id}`,
                    expiresAt: payload.expires_at || null,
                    verifyUrl: bootstrap.verifyUrl,
                });
            })
            .catch(() => {
                if (active) clearSession();
            });

        return () => {
            active = false;
        };
    }, [searchParams, clearSession, setLoading, setSession]);

    if (loading) {
        return <main className="flex h-full items-center justify-center text-sm text-stone-500">会话校验中...</main>;
    }

    if (!authenticated) {
        return (
            <main className="flex h-full items-center justify-center bg-background px-6 text-center">
                <section className="max-w-md rounded-3xl border border-stone-200 bg-white p-8 shadow-sm">
                    <h1 className="text-xl font-semibold text-stone-900">未授权</h1>
                    <p className="mt-3 text-sm text-stone-600">请从主站重新进入画布，主站登录态失效后这里不会继续开放编辑能力。</p>
                </section>
            </main>
        );
    }

    return <>{children}</>;
}
```

- [ ] **Step 4: 把项目列表页和编辑页包进同一个 guard**

```tsx
// D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/page.tsx
"use client";

import { CanvasHostSessionGuard } from "./components/canvas-host-session-guard";

export default function CanvasPage() {
    return (
        <CanvasHostSessionGuard>
            <CanvasProjectsPage />
        </CanvasHostSessionGuard>
    );
}
```

```tsx
// D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/[id]/page.tsx
import CanvasClientPage from "./canvas-client-page";
import { CanvasHostSessionGuard } from "../components/canvas-host-session-guard";

export default function CanvasPage() {
    return (
        <CanvasHostSessionGuard>
            <CanvasClientPage />
        </CanvasHostSessionGuard>
    );
}
```

> 执行时把当前 `page.tsx` 里的原逻辑重命名为 `CanvasProjectsPage` 或拆到相邻文件里，避免把现有项目列表实现直接丢掉。

- [ ] **Step 5: 重新运行测试，确认 guard 已接管两个入口页**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_host_session_guard_has_loading_and_unauthorized_states D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_pages_are_wrapped_by_host_session_guard -v
```

Expected:

- 2 passed

- [ ] **Step 6: 构建画布项目，确认没有 TS/Next 编译错误**

Run:

```powershell
npm --prefix 'D:\AI\infinite-canvas\infinite-canvas\web' run build
```

Expected:

- `next build` 成功
- 没有因新增 guard、query 读取或 store 引入导致的编译错误

- [ ] **Step 7: 记录检查点**

```powershell
git rev-parse --is-inside-work-tree
git add D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\components\canvas-host-session-guard.tsx D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\page.tsx D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\[id]\page.tsx D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py
git commit -m "feat: guard canvas pages behind host session"
```

---

### Task 5: 让身份上下文可被画布后续计费和权限能力复用

**Files:**
- Modify: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/components/canvas-host-session-guard.tsx`
- Modify: `D:/AI/infinite-canvas/infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Modify: `D:/AI/huishihuabu/tests/test_canvas_identity_phase1_external.py`

- [ ] **Step 1: 先写失败测试，锁定编辑页至少读取一次 host session store**

```python
def test_canvas_client_page_reads_host_session_store():
    source = (CANVAS_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")

    assert "useCanvasHostSessionStore" in source
    assert "billingIdentity" in source
    assert "role" in source
```

- [ ] **Step 2: 运行测试，确认先失败**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_client_page_reads_host_session_store -v
```

Expected:

- 失败，原因是编辑页还未读取身份 store。

- [ ] **Step 3: 在编辑页读取身份上下文，并把它固定成后续动作的公共来源**

```tsx
import { useCanvasHostSessionStore } from "../stores/use-canvas-host-session-store";

function InfiniteCanvasPage() {
    const hostUserId = useCanvasHostSessionStore((state) => state.userId);
    const hostRole = useCanvasHostSessionStore((state) => state.role);
    const billingIdentity = useCanvasHostSessionStore((state) => state.billingIdentity);

    const canAccessAdminDiagnostics = hostRole === "admin";

    useEffect(() => {
        if (!hostUserId || !billingIdentity) return;
        console.debug("canvas host session ready", {
            hostUserId,
            hostRole,
            billingIdentity,
        });
    }, [hostUserId, hostRole, billingIdentity]);

    return (
        <main className="flex h-full min-h-0 overflow-hidden">
            {canAccessAdminDiagnostics ? <div data-canvas-admin-role="true" hidden /> : null}
            {/* 保留现有画布主界面 */}
        </main>
    );
}
```

> 这里不要提前接入真正扣费，也不要把 `billingIdentity` 拼进现有生成 API。第 1 阶段只要求“编辑页能拿到且统一来源固定”，后续扣费接口直接复用这一上下文。

- [ ] **Step 4: 重新运行测试，确认编辑页已经接上统一身份源**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py::test_canvas_client_page_reads_host_session_store -v
```

Expected:

- 1 passed

- [ ] **Step 5: 再跑一次画布构建，确认编辑页接入 store 后仍可编译**

Run:

```powershell
npm --prefix 'D:\AI\infinite-canvas\infinite-canvas\web' run build
```

Expected:

- `next build` 成功

- [ ] **Step 6: 记录检查点**

```powershell
git rev-parse --is-inside-work-tree
git add D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\[id]\canvas-client-page.tsx D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py
git commit -m "feat: surface host identity inside canvas editor"
```

---

### Task 6: 全量回归与阶段验收

**Files:**
- Test only: `D:/AI/huishihuabu/tests/test_canvas_identity_session.py`
- Test only: `D:/AI/huishihuabu/tests/test_canvas_identity_phase1_external.py`
- Test only: `D:/AI/huishihuabu/tests/test_settings_config_status.py`
- Test only: `D:/AI/huishihuabu/tests/test_package_defaults.py`
- Test only: `D:/AI/huishihuabu/tests/test_workspace_generation_flow.py`

- [ ] **Step 1: 跑主站全部相关回归**

Run:

```powershell
& 'D:\AI\huishihuabu\.venv\Scripts\python.exe' -m pytest D:\AI\huishihuabu\tests\test_canvas_identity_session.py D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py D:\AI\huishihuabu\tests\test_settings_config_status.py D:\AI\huishihuabu\tests\test_package_defaults.py D:\AI\huishihuabu\tests\test_workspace_generation_flow.py -q
```

Expected:

- 全部通过
- 已有的配置中心、计费、独立画布页、资产桥接回归不被破坏

- [ ] **Step 2: 跑画布项目构建回归**

Run:

```powershell
npm --prefix 'D:\AI\infinite-canvas\infinite-canvas\web' run build
```

Expected:

- `next build` 成功

- [ ] **Step 3: 做人工验收**

按下面顺序手测：

1. 登录主站账号后访问 `http://127.0.0.1:8000/canvas`。
2. 确认 iframe 地址包含 `host_mode=huishi`、`host_session_token`、`host_session_verify_url`。
3. 确认画布项目列表页能正常显示，而不是直接进入匿名模式。
4. 打开任意画布项目，确认编辑页能正常渲染。
5. 打开浏览器开发者工具，确认主站 `POST /api/canvas/session/verify` 返回 `authenticated: true`。
6. 手动删掉 iframe URL 里的 `host_session_token` 后刷新，确认画布停留在“未授权”界面。
7. 从主站资产页发送素材到画布，确认 `huishi-canvas-import` / `huishi-canvas-ready` / `huishi-canvas-ping` 仍然工作。

- [ ] **Step 4: 记录最终检查点**

```powershell
git rev-parse --is-inside-work-tree
git add D:\AI\huishihuabu\huishi\canvas_session.py D:\AI\huishihuabu\huishi\routes_workspace.py D:\AI\huishihuabu\huishi\config.py D:\AI\huishihuabu\templates\canvas.html D:\AI\huishihuabu\tests\test_canvas_identity_session.py D:\AI\huishihuabu\tests\test_canvas_identity_phase1_external.py D:\AI\huishihuabu\tests\test_workspace_generation_flow.py D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\lib\host-canvas-session.ts D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\stores\use-canvas-host-session-store.ts D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\components\canvas-host-session-guard.tsx D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\page.tsx D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\[id]\page.tsx D:\AI\infinite-canvas\infinite-canvas\web\src\app\(user)\canvas\[id]\canvas-client-page.tsx
git commit -m "feat: integrate canvas identity with host session"
```

---

## 计划自检

### 1. Spec 覆盖检查

- “主站是唯一身份源”：Task 1、Task 2
- “画布不自建账号体系”：Task 4
- “主站签发短时 canvas session token”：Task 1、Task 2
- “画布 bootstrap 校验 token，识别 user_id / role / billing_identity”：Task 3、Task 4、Task 5
- “未授权/过期不能进入编辑态”：Task 4、Task 6
- “不混入结果回流 / 资产分类 / runtime 一键启动”：Task 5 的说明中明确只读身份，不接扣费、不接回流

### 2. Placeholder 扫描

本计划没有使用：

- `TODO`
- `TBD`
- “后续补充实现”
- “类似上一步”
- 省略号式代码占位

### 3. 类型与命名一致性检查

- 主站 token 名称统一为 `canvas session token`
- query 参数统一为 `host_mode`、`host_session_token`、`host_session_verify_url`、`host_origin`
- 画布 store 字段统一为 `authenticated`、`userId`、`role`、`billingIdentity`、`expiresAt`
- 校验接口统一为 `POST /api/canvas/session/verify`

### 4. 范围约束复核

本计划明确不做：

- 画布结果回流主站资产库
- 资产分类升级为“全部 / 图片 / 画布”
- 画布内真实扣费动作
- Agent/MCP 一键启动
- 双系统用户表、用户映射表

这些内容都必须等第 1 阶段完成后，基于已经落地的 `billingIdentity` 和 host session 再开下一份计划。
