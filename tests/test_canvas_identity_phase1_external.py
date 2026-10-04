"""
画布身份集成测试（Phase 1）
画布项目路径由环境变量 HUISHI_CANVAS_PROJECT_DIR 控制，未设置则跳过。
"""
from pathlib import Path
import os
import pytest

_CANVAS_ROOT_ENV = os.environ.get("HUISHI_CANVAS_PROJECT_DIR", "")
CANVAS_ROOT = Path(_CANVAS_ROOT_ENV) / "web/src/app/(user)/canvas" if _CANVAS_ROOT_ENV else None

canvas_project = pytest.mark.skipif(
    CANVAS_ROOT is None or not CANVAS_ROOT.exists(),
    reason="HUISHI_CANVAS_PROJECT_DIR not set or canvas project not found",
)


@canvas_project
def test_canvas_host_session_helper_defines_verify_contract():
    source = (CANVAS_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")
    assert "export type HostCanvasSessionPayload" in source
    assert "host_session_token" in source
    assert "host_session_verify_url" in source
    assert "verifyHostCanvasSession" in source


@canvas_project
def test_canvas_host_session_store_exposes_billing_identity():
    source = (CANVAS_ROOT / "stores/use-canvas-host-session-store.ts").read_text(encoding="utf-8")
    assert "billingIdentity" in source
    assert "authenticated" in source
    assert "expiresAt" in source
    assert "setSession" in source
    assert "clearSession" in source


@canvas_project
def test_canvas_host_session_guard_has_loading_and_unauthorized_states():
    source = (CANVAS_ROOT / "components/canvas-host-session-guard.tsx").read_text(encoding="utf-8")
    assert "verifyHostCanvasSession" in source
    assert "useCanvasHostSessionStore" in source


@canvas_project
def test_canvas_host_session_guard_allows_standalone_canvas():
    guard_source = (CANVAS_ROOT / "components/canvas-host-session-guard.tsx").read_text(encoding="utf-8")
    store_source = (CANVAS_ROOT / "stores/use-canvas-host-session-store.ts").read_text(encoding="utf-8")
    assert "requiresHostSession" in store_source
    assert "setStandalone" in store_source
    assert "if (!requiresHostSession) return <>{children}</>;" in guard_source
    assert "setStandalone();" in guard_source


@canvas_project
def test_canvas_host_session_guard_rejects_incomplete_host_bootstrap():
    guard_source = (CANVAS_ROOT / "components/canvas-host-session-guard.tsx").read_text(encoding="utf-8")
    helper_source = (CANVAS_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")
    assert "export function isHostCanvasMode" in helper_source
    assert "isHostCanvasMode(searchParams)" in guard_source
    assert "if (!isHostCanvasMode(searchParams))" in guard_source
    assert "if (!bootstrap) {" in guard_source
    assert "clearSession();" in guard_source[guard_source.index("if (!bootstrap) {") :]


@canvas_project
def test_canvas_pages_are_wrapped_by_host_session_guard():
    page_source = (CANVAS_ROOT / "page.tsx").read_text(encoding="utf-8")
    detail_source = (CANVAS_ROOT / "[id]/page.tsx").read_text(encoding="utf-8")
    assert "CanvasHostSessionGuard" in page_source
    assert "CanvasHostSessionGuard" in detail_source


@canvas_project
def test_canvas_client_page_reads_host_session_store():
    source = (CANVAS_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    assert "useCanvasHostSessionStore" in source
    assert "hostEmbedded" in source


@canvas_project
def test_canvas_host_session_store_exposes_generate_url():
    source = (CANVAS_ROOT / "stores/use-canvas-host-session-store.ts").read_text(encoding="utf-8")
    assert "generateUrl" in source


@canvas_project
def test_canvas_bootstrap_reads_host_generate_url():
    source = (CANVAS_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")
    assert "host_generate_url" in source
    assert "generateUrl" in source
