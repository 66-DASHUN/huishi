"""
画布嵌入契约测试：验证 Flask 模板和画布前端已正确实现宿主嵌入模式。
画布项目路径由环境变量 HUISHI_CANVAS_PROJECT_DIR 控制，未设置则跳过画布侧断言。
"""
from pathlib import Path
import os
import pytest

# 主站模板路径（始终可读）
HUISHI_ROOT = Path(__file__).parent.parent

# 画布前端路径（可选，未配置时跳过画布侧测试）
_CANVAS_ROOT_ENV = os.environ.get("HUISHI_CANVAS_PROJECT_DIR", "")
CANVAS_SRC_ROOT = Path(_CANVAS_ROOT_ENV) / "web/src" if _CANVAS_ROOT_ENV else None
CANVAS_WEB_ROOT = CANVAS_SRC_ROOT / "app/(user)/canvas" if CANVAS_SRC_ROOT else None

canvas_project_available = pytest.mark.skipif(
    CANVAS_WEB_ROOT is None or not CANVAS_WEB_ROOT.exists(),
    reason="HUISHI_CANVAS_PROJECT_DIR not set or canvas project not found",
)


@canvas_project_available
def test_canvas_projects_page_treats_host_session_as_embedded_entry():
    source = (CANVAS_WEB_ROOT / "page.tsx").read_text(encoding="utf-8")
    assert 'const hostEmbedded = searchParams.get("host_mode") === "huishi";' in source
    assert 'const effectiveMode = mode || (hostEmbedded ? "recent" : null);' in source
    assert "if (hostEmbedded) return;" in source
    assert 'if (!hydrated || autoOpenRef.current || effectiveMode !== "recent") return;' in source


@canvas_project_available
def test_canvas_editor_keeps_top_bar_in_host_embedded_mode():
    source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    assert 'const hostEmbedded = searchParams.get("host_mode") === "huishi";' in source
    assert "<CanvasTopBar" in source


@canvas_project_available
def test_canvas_top_bar_hides_global_config_action():
    source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    assert "<UserStatusActions showConfig={false}" in source


@canvas_project_available
def test_global_config_action_routes_to_settings_page():
    source = (CANVAS_SRC_ROOT / "components/layout/user-status-actions.tsx").read_text(encoding="utf-8")
    assert 'router.push("/settings")' in source
    assert "openConfigDialog" not in source
    assert "setConfigDialogOpen" not in source


@canvas_project_available
def test_canvas_sources_do_not_open_legacy_config_modal():
    canvas_sources = [
        CANVAS_WEB_ROOT / "page.tsx",
        CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx",
        *list((CANVAS_WEB_ROOT / "components").glob("*.tsx")),
    ]
    offenders = []
    for path in canvas_sources:
        source = path.read_text(encoding="utf-8")
        if "openConfigDialog" in source or "AppConfigModal" in source:
            offenders.append(str(path.relative_to(CANVAS_SRC_ROOT)))
    assert offenders == []


@canvas_project_available
def test_canvas_new_project_titles_use_next_available_number():
    list_source = (CANVAS_WEB_ROOT / "page.tsx").read_text(encoding="utf-8")
    editor_source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    helper_source = (CANVAS_WEB_ROOT / "utils/canvas-project-title.ts").read_text(encoding="utf-8")
    editor_create_source = editor_source[
        editor_source.index("const createAndOpenProject") : editor_source.index("const deleteCurrentProject")
    ]

    assert "nextCanvasProjectTitle" in helper_source
    assert 'new RegExp(`^${escapeRegExp(prefix)}(?:\\\\s*(\\\\d+))?$`)' in helper_source
    assert "createProject(nextCanvasProjectTitle(projects, \"新建画布\"));" in list_source
    assert "nextCanvasProjectTitle(projects, \"新建画布\")" in list_source
    assert "enterProject(createProject" not in list_source
    assert "nextCanvasProjectTitle(projects, \"无限画布\")" not in list_source
    assert "nextCanvasProjectTitle(useCanvasStore.getState().projects, \"新建画布\")" in editor_source
    assert "nextCanvasProjectTitle(useCanvasStore.getState().projects, \"无限画布\")" not in editor_source
    assert "router.push(`/canvas/${id}" not in editor_create_source
    assert "router.push(`/canvas${hostSessionQuery ? `?${hostSessionQuery}` : \"\"}`);" in editor_create_source
    assert "projects.length + 1" not in list_source
    assert "projects.length + 1" not in editor_source


@canvas_project_available
def test_canvas_mode_new_creates_project_without_opening_editor():
    source = (CANVAS_WEB_ROOT / "page.tsx").read_text(encoding="utf-8")
    mode_new_source = source[source.index('if (effectiveMode === "new")') : source.index('if (!hydrated || autoOpenRef.current || effectiveMode !== "recent")')]

    assert "createProject(nextCanvasProjectTitle(projects, \"新建画布\"));" in mode_new_source
    assert "enterProject" not in mode_new_source
    assert "router.replace" in mode_new_source


@canvas_project_available
def test_canvas_agent_config_entry_respects_host_session():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    host_session_source = (CANVAS_WEB_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")
    assert "openConfigDialog" not in source
    assert "canvasSettingsHref(hostOrigin, requiresHostSession)" in source
    assert 'return hostSettingsHref(hostOrigin) || (requiresHostSession ? "" : "/settings?tab=channels");' in host_session_source
    assert "/settings?tab=channels" not in source


@canvas_project_available
def test_canvas_host_tool_followup_uses_chat_completion_messages():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")

    assert "function toolCallsToChatMessage(calls: ResponseToolCall[])" in source
    assert 'role: "assistant" as const' in source
    assert "tool_calls: calls.map" in source
    assert "hostChatProxy ? [...messages, toolCallsToChatMessage(toolCalls), ...toolResultMessages]" in source


@canvas_project_available
def test_canvas_agent_prompt_keeps_conversation_inside_creative_scope():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")

    assert "\u4f60\u662f\u7ed8\u4e16\u521b\u4f5c Agent" in source
    assert "\u751f\u56fe\u8bbe\u8ba1\u3001\u63d0\u793a\u8bcd\u3001\u7d20\u6750\u5206\u6790" in source
    assert "\u5e7f\u544a\u6587\u6848\u3001\u54c1\u724c\u7b56\u5212" in source
    assert "\u660e\u663e\u65e0\u5173\u7684\u95ee\u9898" in source
    assert "\u4e0d\u8c03\u7528\u4efb\u4f55\u753b\u5e03\u5de5\u5177" in source


@canvas_project_available
def test_canvas_online_agent_only_includes_full_snapshot_for_explicit_canvas_requests():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    messages_source = (CANVAS_WEB_ROOT / "utils/canvas-agent-messages.ts").read_text(encoding="utf-8")
    tools_source = source[source.index("const ONLINE_AGENT_TOOLS") : source.index("type OnlineAgentTab")]
    prompt_source = source[source.index("const ONLINE_AGENT_PROMPT") : source.index("const AGENT_QUICK_ACTIONS")]

    assert 'toolDefinition("canvas_get_state"' not in tools_source
    assert 'toolDefinition("canvas_get_selection"' not in tools_source
    assert 'toolDefinition("canvas_export_snapshot"' not in tools_source
    assert '"canvas_create_image_prompt_flow"' not in tools_source
    assert "\u753b\u5e03\u5feb\u7167\u4ec5\u5728\u7528\u6237\u660e\u786e\u8981\u6c42\u753b\u5e03\u64cd\u4f5c\u6216\u5206\u6790\u65f6\u63d0\u4f9b" in prompt_source
    assert "\u4e0d\u8981\u91cd\u590d\u8bfb\u53d6\u6574\u5f20\u753b\u5e03" in prompt_source
    assert "function shouldIncludeCanvasSnapshot(text: string)" in messages_source
    assert "shouldIncludeCanvasSnapshot(userMessage.text)" in messages_source
    assert "...(canvasContext ? [{ type: \"text\" as const, text: canvasContext }] : [])" in messages_source
    assert "buildToolAgentMessages(snapshotRef.current" in source
    assert '"canvas_apply_ops"' not in tools_source
    assert '"canvas_create_node"' not in tools_source
    assert '"canvas_create_config_node"' not in tools_source
    assert '"canvas_generate_image"' in tools_source


@canvas_project_available
def test_canvas_agent_image_generation_uses_one_inline_image_node():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    dispatch_source = source[source.index("function onlineToolToOps") : source.index("function generationFlowOps")]
    helper_source = source[source.index("function imageGenerationOps") : source.index("function generationFlowOps")]

    assert 'if (name === "canvas_generate_image") return imageGenerationOps(input, snapshot, config);' in dispatch_source
    assert 'if (name === "canvas_create_image_prompt_flow") return imageGenerationOps(input, snapshot, config);' in dispatch_source
    assert 'generationMode(input.mode) === "image" ? imageGenerationOps(input, snapshot, config) : generationFlowOps(input, snapshot, config)' in dispatch_source
    assert "nodeType: CanvasNodeType.Image" in helper_source
    assert "generationCount(config.canvasImageCount || config.count)" in helper_source
    assert 'runGenerationOp(imageId, "image", prompt)' in helper_source
    assert "textNodeOp(" not in helper_source
    assert "configNodeOp(" not in helper_source


@canvas_project_available
def test_canvas_agent_generation_requests_are_queued():
    source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    apply_source = source[source.index("const applyAgentOps") : source.index("const undoAgentOps")]

    assert "agentGenerationQueueRef" in source
    assert "agentGenerationQueueRef.current = agentGenerationQueueRef.current" in apply_source
    assert "await generateNodeRef.current?." in apply_source
    assert "generationOps.forEach" not in apply_source


@canvas_project_available
def test_canvas_agent_quick_actions_focus_on_creation_not_full_canvas_inspection():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    actions_source = source[source.index("const AGENT_QUICK_ACTIONS") : source.index("const JSON_RECORD_SCHEMA")]

    assert "\u4f18\u5316\u5f53\u524d\u63d0\u793a\u8bcd" in actions_source
    assert "\u751f\u6210\u4e00\u5f20\u4e3b\u89c6\u89c9" in actions_source
    assert "\u89e3\u91ca\u5f53\u524d\u753b\u5e03\u7ed3\u6784" not in actions_source


@canvas_project_available
def test_canvas_select_icon_does_not_use_radix_slot_ref_composition():
    source = (CANVAS_SRC_ROOT / "components/ui/select.tsx").read_text(encoding="utf-8")

    assert "<SelectPrimitive.Icon asChild>" not in source
    assert "<SelectPrimitive.Icon>" in source


@canvas_project_available
def test_canvas_model_picker_does_not_mount_radix_select():
    source = (CANVAS_SRC_ROOT / "components/model-picker.tsx").read_text(encoding="utf-8")

    assert 'import { Select } from "antd";' in source
    assert 'from "@/components/ui/select"' not in source
    assert "SelectPrimitive" not in source


@canvas_project_available
def test_canvas_agent_sessions_have_one_way_parent_persistence():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")

    assert "setLocalSessions(sessions);" not in source
    assert "onSessionsChange(localSessions, localActiveSessionId);" in source
    assert "useState<CanvasAssistantSession[]>(() => (sessions.length ? sessions" in source


@canvas_project_available
def test_canvas_agent_image_settings_button_uses_local_popover():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    popover_source = (CANVAS_WEB_ROOT / "components/canvas-image-settings-popover.tsx").read_text(encoding="utf-8")
    assert "CanvasImageSettingsPopover" in source
    assert "showLabel={false}" in source
    assert "showLabel?: boolean" in popover_source
    assert "ariaLabel?: string" in popover_source
    assert "aria-label={ariaLabel}" in popover_source
    assert "TODO: 打开图像设置面板" not in source
    assert "图像设置" in source


@canvas_project_available
def test_canvas_agent_composer_uses_settings_text_model_without_inline_picker():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    composer_source = source[source.index("<AgentChatComposer") : source.index("<Modal", source.index("<AgentChatComposer"))]

    assert "effectiveConfig.textModel || effectiveConfig.model" in source
    assert "AgentTextModelPicker" not in source
    assert "CanvasPromptLibrary" not in composer_source
    assert "AgentQuickActions" in source
    assert "\u6574\u7406\u5f53\u524d\u753b\u5e03" not in source
    assert "\u4f18\u5316\u5f53\u524d\u63d0\u793a\u8bcd" in source
    assert "\u751f\u6210\u4e00\u5f20\u4e3b\u89c6\u89c9" in source
    assert "\u68c0\u67e5\u672a\u8fde\u63a5\u8282\u70b9" not in source
    assert "\u89e3\u91ca\u5f53\u524d\u753b\u5e03\u7ed3\u6784" not in source

@canvas_project_available
def test_canvas_online_agent_surfaces_host_stream_errors():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    assert "if (chunk.error) throw new Error(formatHostChatError(chunk.error));" in source
    assert 'buffer.split("\\n\\n")' in source
    assert "无法连接主站 Agent 代理" in source


@canvas_project_available
def test_canvas_online_agent_errors_can_retry_original_prompt():
    panel_source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    chat_source = (CANVAS_WEB_ROOT / "components/canvas-agent-chat-ui.tsx").read_text(encoding="utf-8")
    assert "retryText: userMessage.text" in panel_source
    assert "onRetryError" in panel_source
    assert "setPrompt(retryText)" in panel_source
    assert "onRetryError?.(item)" in chat_source
    assert "重试" in chat_source


@canvas_project_available
def test_canvas_online_agent_uses_host_proxy_for_followup_tool_loop():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    followup_source = source[source.index("const continueOnlineToolLoopAfterResults") : source.index("const executeOps")]
    assert "hostChatProxy" in followup_source
    assert "requestHostTextChat(hostChatProxy.chatUrl" in followup_source


@canvas_project_available
def test_canvas_online_agent_uses_auto_tool_choice_on_first_step():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    first_step_source = source[source.index("const runOnlineAgentStep") : source.index("const continueOnlineToolLoop")]

    assert '{ toolChoice: "auto" }' in first_step_source
    assert 'ONLINE_AGENT_TOOLS, "auto"' in first_step_source
    assert 'ONLINE_AGENT_TOOLS, "required"' not in first_step_source


@canvas_project_available
def test_canvas_host_chat_helper_keeps_stream_callback_signature():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    assert 'toolChoice: "auto" | "none", onStreaming: (text: string) => void' in source
    assert 'Promise<{ content: string; toolCalls: ResponseToolCall[] }>' in source


@canvas_project_available
def test_canvas_agent_does_not_force_tools_and_always_confirms_destructive_calls():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    prompt_source = source[source.index("const ONLINE_AGENT_PROMPT") : source.index("const AGENT_QUICK_ACTIONS")]
    assert "\u9996\u8f6e\u5fc5\u987b\u8c03\u7528\u5de5\u5177" not in prompt_source
    assert "\u666e\u901a\u95ee\u7b54\u53ef\u76f4\u63a5\u56de\u7b54" in prompt_source
    assert "ONLINE_DESTRUCTIVE_TOOLS" in source
    assert "requiresToolConfirmation" in source

    assert "\u4e0d\u8981\u4e3b\u52a8\u5efa\u8bae\u6e05\u7406" in prompt_source

@canvas_project_available
def test_canvas_agent_never_falls_back_to_local_credentials_in_host_mode():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    send_source = source[source.index("const sendMessage") : source.index("const runOnlineAgentStep")]
    settings_source = source[source.index("const openChannelSettings") : source.index("const sendMessage")]
    assert "requiresHostSession && !hostChatProxy" in send_source
    assert "\u4e3b\u7ad9\u4f1a\u8bdd\u5df2\u5931\u6548" in send_source
    assert "canvasSettingsHref(hostOrigin, requiresHostSession)" in settings_source
    assert 'hostSettingsHref(hostOrigin) || "/settings?tab=channels"' not in settings_source


@canvas_project_available
def test_canvas_host_bootstrap_rejects_untrusted_origins():
    source = (CANVAS_WEB_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")
    assert "window.parent === window" in source
    assert "document.referrer" in source
    assert "isTrustedHostFrameOrigin" in source
    assert "hasOrigin" in source
    guard_source = (CANVAS_WEB_ROOT / "components/canvas-host-session-guard.tsx").read_text(encoding="utf-8")
    assert "if (authenticated) return;" in guard_source


@canvas_project_available
def test_canvas_toolbar_centers_when_embedded_agent_panel_is_closed():
    toolbar_source = (CANVAS_WEB_ROOT / "components/canvas-toolbar.tsx").read_text(encoding="utf-8")
    editor_source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    assert "leftGutter" not in toolbar_source
    toolbar = editor_source[editor_source.index("<CanvasToolbar") : editor_source.index("</section>", editor_source.index("<CanvasToolbar"))]
    assert "leftGutter" not in toolbar


@canvas_project_available
def test_canvas_prompt_api_filters_empty_cover_items():
    source = (CANVAS_SRC_ROOT / "app/api/prompts/route.ts").read_text(encoding="utf-8")
    assert "item.coverUrl.trim()" in source
    assert "settled.flat().filter" in source


@canvas_project_available
def test_canvas_prompt_card_falls_back_when_cover_image_fails():
    source = (CANVAS_SRC_ROOT / "components/prompts/prompt-card.tsx").read_text(encoding="utf-8")
    assert "coverFailed" in source
    assert "setCoverFailed(true)" in source
    assert "onError" in source
    assert "No preview" in source


@canvas_project_available
def test_canvas_prompt_detail_does_not_show_raw_preview_block():
    source = (CANVAS_SRC_ROOT / "components/prompts/prompt-detail-dialog.tsx").read_text(encoding="utf-8")
    assert "prompt.preview" not in source
    assert "<pre" not in source


@canvas_project_available
def test_canvas_prompt_library_lives_at_asset_lower_left():
    source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    assert "PromptSelectDialog" in source
    assert "data-canvas-prompt-library-anchor" in source
    assert "bottom-24 left-5" in source
    assert "createPromptTextNode" in source


@canvas_project_available
def test_canvas_top_navigation_removes_standalone_prompt_library():
    source = (CANVAS_SRC_ROOT / "constant/navigation-tools.ts").read_text(encoding="utf-8")
    assert 'slug: "prompts"' not in source
    assert 'label: "提示词库"' not in source
    assert "FileText" not in source


@canvas_project_available
def test_canvas_config_import_does_not_accept_credentials_from_url():
    source = (CANVAS_SRC_ROOT / "components/layout/client-root-init.tsx").read_text(encoding="utf-8")
    assert 'searchParams.get("baseUrl")' not in source
    assert 'searchParams.get("apiKey")' not in source
    assert 'searchParams.get("apikey")' not in source
    assert "router.push('/settings?tab=channels')" not in source
    assert 'router.push("/settings?tab=channels")' not in source


@canvas_project_available
def test_canvas_host_embedded_urls_clean_all_host_params():
    expected_params = [
        "host_mode",
        "host_session_token",
        "host_session_verify_url",
        "host_assets_library_url",
        "host_generate_url",
        "host_chat_url",
        "host_user_key_url",
        "host_user_key_enabled",
        "host_origin",
    ]
    sources = [
        CANVAS_WEB_ROOT / "page.tsx",
        CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx",
    ]
    for path in sources:
        source = path.read_text(encoding="utf-8")
        missing = [param for param in expected_params if f'"{param}"' not in source]
        assert missing == [], f"{path.relative_to(CANVAS_SRC_ROOT)} missing cleanup for {missing}"


@canvas_project_available
def test_canvas_host_estimate_requests_are_abortable():
    source = (CANVAS_SRC_ROOT / "services/api/host-image.ts").read_text(encoding="utf-8")
    estimate_source = source[source.index("export async function requestHostEstimate") :]
    assert "signal?: AbortSignal" in estimate_source
    assert "signal: opts.signal" in estimate_source

    hook_source = (CANVAS_WEB_ROOT / "hooks/use-host-credits.ts").read_text(encoding="utf-8")
    assert "signal: ctrl.signal" in hook_source


@canvas_project_available
def test_canvas_host_estimate_abort_does_not_emit_console_error():
    hook_source = (CANVAS_WEB_ROOT / "hooks/use-host-credits.ts").read_text(encoding="utf-8")
    assert 'err instanceof DOMException && err.name === "AbortError"' in hook_source
    assert "console.error" not in hook_source
    assert "console.log" not in hook_source


@canvas_project_available
def test_canvas_host_embedded_config_entries_route_to_host_settings():
    session_store = (CANVAS_WEB_ROOT / "stores/use-canvas-host-session-store.ts").read_text(encoding="utf-8")
    host_session_lib = (CANVAS_WEB_ROOT / "lib/host-canvas-session.ts").read_text(encoding="utf-8")
    prompt_panel = (CANVAS_WEB_ROOT / "components/canvas-node-prompt-panel.tsx").read_text(encoding="utf-8")
    config_panel = (CANVAS_WEB_ROOT / "components/canvas-config-node-panel.tsx").read_text(encoding="utf-8")
    assistant_panel = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")

    assert "hostOrigin: string;" in session_store
    assert "hostOrigin: payload.hostOrigin" in session_store
    assert "export function hostSettingsHref" in host_session_lib
    assert "export function canvasSettingsHref" in host_session_lib
    assert "new URL(\"/admin/config/settings\", hostOrigin)" in host_session_lib
    assert "canvasSettingsHref(hostOrigin, requiresHostSession)" in prompt_panel
    assert "canvasSettingsHref(hostOrigin, requiresHostSession)" in config_panel
    assert "canvasSettingsHref(hostOrigin, requiresHostSession)" in assistant_panel
    assert 'hostSettingsHref(hostOrigin) || "/settings?tab=channels"' not in assistant_panel


@canvas_project_available
def test_canvas_generation_navigation_prompts_before_leaving():
    guard_source = (CANVAS_WEB_ROOT / "lib/canvas-navigation-guard.ts").read_text(encoding="utf-8")
    editor_source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    session_store = (CANVAS_WEB_ROOT / "stores/use-canvas-host-session-store.ts").read_text(encoding="utf-8")
    prompt_panel = (CANVAS_WEB_ROOT / "components/canvas-node-prompt-panel.tsx").read_text(encoding="utf-8")
    config_panel = (CANVAS_WEB_ROOT / "components/canvas-config-node-panel.tsx").read_text(encoding="utf-8")
    assistant_panel = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")

    assert "画布正在生成" in guard_source
    assert "window.confirm" in guard_source
    assert "navigateFromCanvas" in guard_source
    assert "isGenerating: boolean;" in session_store
    assert "setGenerating: (isGenerating: boolean) => void;" in session_store
    assert "setGenerating(runningNodeId !== null)" in editor_source
    assert "confirmCanvasNavigation(isGenerating)" in editor_source
    assert "navigateFromCanvas(settingsHref, isGenerating)" in prompt_panel
    assert "navigateFromCanvas(settingsHref, isGenerating)" in config_panel
    assert "navigateFromCanvas(settingsHref, isGenerating)" in assistant_panel


@canvas_project_available
def test_canvas_host_estimate_posts_json_without_token_query_string():
    source = (CANVAS_SRC_ROOT / "services/api/host-image.ts").read_text(encoding="utf-8")
    estimate_source = source[source.index("export async function requestHostEstimate") :]
    assert 'method: "POST"' in estimate_source
    assert '"Content-Type": "application/json"' in estimate_source
    assert "body: JSON.stringify" in estimate_source
    assert "new URLSearchParams" not in estimate_source
    assert "/estimate?" not in estimate_source
    assert "token: proxy.token" in estimate_source


@canvas_project_available
def test_canvas_local_agent_fetches_send_token_in_header_not_query_string():
    source = (CANVAS_WEB_ROOT / "components/canvas-local-agent-panel.tsx").read_text(encoding="utf-8")
    assert '"x-canvas-agent-token"' in source
    assert "new EventSource(`${endpoint}/events?token=" in source
    assert "/agent/codex/turn?token=" not in source
    assert "/canvas/state?token=" not in source
    assert "/canvas/result?token=" not in source
    assert "token=${encodeURIComponent(token)}" not in source[source.index("async function fetchAgentJson") :]


@canvas_project_available
def test_canvas_api_error_messages_are_redacted_before_display():
    helper_source = (CANVAS_SRC_ROOT / "lib/error-sanitizer.ts").read_text(encoding="utf-8")
    assert "redactSensitiveErrorMessage" in helper_source
    for marker in ("Bearer", "api[_-]?key", "token", "password", "sk|sess|key"):
        assert marker in helper_source

    for service_name in ("image.ts", "audio.ts", "video.ts"):
        source = (CANVAS_SRC_ROOT / f"services/api/{service_name}").read_text(encoding="utf-8")
        assert 'from "@/lib/error-sanitizer"' in source
        error_reader = source[source.index("function readAxiosError") :]
        assert "redactSensitiveErrorMessage(" in error_reader


@canvas_project_available
def test_canvas_visible_sources_do_not_contain_mojibake_text():
    mojibake_markers = (
        "\u9422",
        "\u95b0",
        "\u699b",
        "\u5a13",
        "\u7487",
        "\u93b4",
        "\u5bb8",
        "\u934f",
        "\ufffd",
    )
    visible_source_paths = [
        CANVAS_WEB_ROOT / "page.tsx",
        CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx",
        CANVAS_WEB_ROOT / "components/canvas-toolbar.tsx",
        CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx",
        CANVAS_SRC_ROOT / "components/settings/settings-tabs-content.tsx",
        CANVAS_SRC_ROOT / "components/layout/client-root-init.tsx",
        CANVAS_SRC_ROOT / "components/layout/app-top-nav.tsx",
        CANVAS_SRC_ROOT / "components/layout/user-status-actions.tsx",
        CANVAS_SRC_ROOT / "app/(user)/settings/page.tsx",
    ]
    offenders = []
    for path in visible_source_paths:
        source = path.read_text(encoding="utf-8")
        found = [marker for marker in mojibake_markers if marker in source]
        if found:
            offenders.append(f"{path.relative_to(CANVAS_SRC_ROOT)}: {''.join(found)}")
    assert offenders == []


@canvas_project_available
def test_canvas_editor_does_not_emit_debug_console_logs():
    source = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    forbidden = ("console.log", "console.debug", "console.info", "console.warn", "console.error", "debugger;")
    found = [marker for marker in forbidden if marker in source]
    assert found == []


@canvas_project_available
def test_webdav_proxy_does_not_log_full_target_url():
    source = (CANVAS_SRC_ROOT / "app/webdav-proxy/route.ts").read_text(encoding="utf-8")
    assert "url.href" not in source
    assert "webdavLogTarget" in source


@canvas_project_available
def test_webdav_proxy_restricts_forwarded_methods():
    source = (CANVAS_SRC_ROOT / "app/webdav-proxy/route.ts").read_text(encoding="utf-8")
    assert "WEBDAV_PROXY_ALLOWED_METHODS" in source
    for method in ("GET", "HEAD", "PUT", "PROPFIND", "MKCOL"):
        assert f'"{method}"' in source
    assert "Method not allowed" in source
    assert "status: 405" in source


def test_canvas_host_embedded_shell_uses_full_bleed_frame():
    source = (HUISHI_ROOT / "templates/canvas.html").read_text(encoding="utf-8")
    assert "data-canvas-stage" in source
    assert 'loading="eager"' in source
    assert "canvas-frame" in source


def test_canvas_host_shell_posts_selected_theme_to_the_iframe_origin():
    source = (HUISHI_ROOT / "templates/canvas.html").read_text(encoding="utf-8")

    assert "function postThemeToCanvas" in source
    assert 'type: "huishi-theme-change"' in source
    assert "document.documentElement.dataset.themePreference" in source
    assert "document.documentElement.dataset.theme" in source
    assert "url.origin" in source
    assert 'window.addEventListener("huishi-theme-change"' in source


@canvas_project_available
def test_canvas_host_session_guard_shows_inline_text_not_card():
    source = (CANVAS_WEB_ROOT / "components/canvas-host-session-guard.tsx").read_text(encoding="utf-8")
    assert "画布会话未授权，请从主站重新进入。" in source
    assert "max-w-md" not in source
    assert "rounded-3xl" not in source

def test_mobile_canvas_embed_uses_top_navigation_and_full_width_frame():
    css = (HUISHI_ROOT / "static/css/site.css").read_text(encoding="utf-8")

    assert "Product canvas embed mobile" in css
    assert ".canvas-embed-page .studio-shell:not(:has(.studio-sidebar))" in css
    assert "grid-template-columns: 1fr;" in css
    assert "grid-template-rows: 74px minmax(0, 1fr);" in css
    assert ".canvas-embed-page .canvas-main" in css
    assert "height: calc(100svh - 74px);" in css
    assert ".canvas-embed-page .canvas-embed-frame" in css
    assert "min-height: 0;" in css

@canvas_project_available
def test_canvas_image_settings_exposes_count_and_uses_configured_count():
    settings_panel = (CANVAS_SRC_ROOT / "components/image-settings-panel.tsx").read_text(encoding="utf-8")
    popover = (CANVAS_WEB_ROOT / "components/canvas-image-settings-popover.tsx").read_text(encoding="utf-8")
    app_config = (CANVAS_SRC_ROOT / "components/layout/app-config-modal.tsx").read_text(encoding="utf-8")
    config_store = (CANVAS_SRC_ROOT / "stores/use-config-store.ts").read_text(encoding="utf-8")
    client = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    config_panel = (CANVAS_WEB_ROOT / "components/canvas-config-node-panel.tsx").read_text(encoding="utf-8")
    prompt_panel = (CANVAS_WEB_ROOT / "components/canvas-node-prompt-panel.tsx").read_text(encoding="utf-8")

    assert "showCount?: boolean" in settings_panel
    assert "showCount={false}" not in popover
    assert "maxCount={8}" not in popover
    assert "quickCount={4}" not in popover
    assert "maxCount = 10" in settings_panel
    assert "quickCount = 10" in settings_panel
    assert 'canvasImageCount: "1"' in config_store
    assert 'canvasImageCount: config.canvasImageCount || "1"' in config_store
    assert "\\u753b\\u5e03\\u9ed8\\u8ba4\\u751f\\u56fe\\u5f20\\u6570" not in app_config.encode("unicode_escape").decode("ascii")
    build_config = client[client.index("function buildGenerationConfig") : client.index("function resetInterruptedGeneration")]
    assert 'count: String(node?.metadata?.count || (mode === "image" ? config.canvasImageCount || config.count : config.count) || defaultConfig.count)' in build_config
    expected_node_count = 'count: String(node.metadata?.count || (mode === "image" ? globalConfig.canvasImageCount || globalConfig.count : globalConfig.count) || defaultConfig.count)'
    assert expected_node_count in config_panel
    assert expected_node_count in prompt_panel


@canvas_project_available
def test_canvas_generation_count_is_consistently_limited_to_ten():
    helper = CANVAS_SRC_ROOT / "lib/image-generation-count.ts"
    assert helper.exists()
    helper_source = helper.read_text(encoding="utf-8")
    image_api = (CANVAS_SRC_ROOT / "services/api/image.ts").read_text(encoding="utf-8")
    host_api = (CANVAS_SRC_ROOT / "services/api/host-image.ts").read_text(encoding="utf-8")
    client = (CANVAS_WEB_ROOT / "[id]/canvas-client-page.tsx").read_text(encoding="utf-8")
    assistant = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")

    assert "MAX_IMAGE_GENERATION_COUNT = 10" in helper_source
    assert "normalizeImageGenerationCount" in helper_source
    for source in (image_api, host_api, client, assistant):
        assert "normalizeImageGenerationCount" in source


@canvas_project_available
def test_canvas_agent_image_generation_uses_settings_and_visible_position():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    helper = source[source.index("function imageGenerationOps") : source.index("function generationFlowOps")]

    assert "nextVisibleCanvasPosition(snapshot)" in helper
    assert "snapshot.selectedNodeIds" not in helper
    assert "numberOr(input.x" not in helper
    assert "numberOr(input.y" not in helper
    assert 'model: defaultGenerationModel(config, "image")' in helper
    assert "size: config.size" in helper
    assert "quality: config.quality" in helper
    assert "stringOptional(input.size)" not in helper
    assert "stringOptional(input.quality)" not in helper
    assert "stringOptional(input.model)" not in helper
    assert "generationCount(config.canvasImageCount || config.count)" in helper


@canvas_project_available
def test_canvas_agent_limits_each_user_turn_to_one_image_generation_task():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    send_source = source[source.index("const sendMessage") : source.index("const runOnlineAgentStep")]
    execute_source = source[source.index("const executeOnlineToolCall") : source.index("const executeOnlineToolCalls")]

    assert "imageGenerationStartedRef" in source
    assert "imageGenerationStartedRef.current = false" in send_source
    assert 'toolCall.function.name === "canvas_generate_image"' in execute_source
    assert "\\u672c\\u8f6e\\u5df2\\u89e6\\u53d1\\u4e00\\u6b21\\u56fe\\u7247\\u751f\\u6210\\u4efb\\u52a1" in execute_source.encode("unicode_escape").decode("ascii")
    assert "imageGenerationStartedRef.current = true" in execute_source


@canvas_project_available
def test_canvas_agent_tool_result_is_compact_and_does_not_return_full_snapshots():
    source = (CANVAS_WEB_ROOT / "components/canvas-assistant-panel.tsx").read_text(encoding="utf-8")
    execute_ops = source[source.index("const executeOps") : source.index("const executeOnlineTool")]

    assert "opCount: ops.length" in execute_ops
    assert "before: JSON.parse" not in execute_ops
    assert "after: JSON.parse" not in execute_ops
    assert "data: result" not in execute_ops
