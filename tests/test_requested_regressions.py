from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANVAS = ROOT / "infinite-canvas/web/src/app/(user)/canvas"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canvas_batch_generation_uses_one_api_request_for_all_images():
    source = read(CANVAS / "[id]/canvas-client-page.tsx")
    block = source[source.index('if (mode === "image")') : source.index('if (mode === "video")')]
    assert "generatedImages = referenceImages.length" in block
    assert 'count: String(count)' in block
    assert "const image = generatedImages[index]" in block
    assert "Array.from({ length: count - 1 }, () => nanoid())" in block
    assert "const targetIds = [rootId, ...childIds]" in block
    assert "if (count > 1) startGenerationRequest(rootId" not in block
    assert "if (count > 1) finishGenerationRequest(rootId" not in block
    request_map = block[block.index("await Promise.all") :]
    assert "requestGeneration" not in request_map
    assert "requestEdit" not in request_map


def test_canvas_batch_badge_uses_requested_image_count_not_node_count():
    source = read(CANVAS / "[id]/canvas-client-page.tsx")
    batch_map = source[source.index("const batchChildCountById") : source.index("const batchMotionById")]

    assert "node.metadata.count" in batch_map
    assert "normalizeImageGenerationCount" in batch_map


def test_agent_file_picker_processes_every_selected_reference_image():
    source = read(CANVAS / "components/canvas-assistant-panel.tsx")
    block = source[source.index("const addImagesToCanvas") : source.index("const startResize")]
    assert ".filter((item) => item.type.startsWith(\"image/\"))" in block
    assert "await onPasteImages(imageFiles)" in block
    assert "imageFiles.forEach(" not in block
    assert ".find(" not in block


def test_agent_and_inserted_images_use_collision_aware_positions():
    assistant = read(CANVAS / "components/canvas-assistant-panel.tsx")
    client = read(CANVAS / "[id]/canvas-client-page.tsx")
    position = assistant[assistant.index("function nextVisibleCanvasPosition") : assistant.index("function generationFlowOps")]
    assert "snapshot.nodes" in position
    assert "rectanglesOverlap" in position
    assert "findOpenCanvasPosition" in client
    assert "nodesRef.current" in client[client.index("const insertAssistantImage") : client.index("const collectExportableCanvasImages")]


def test_image_nodes_do_not_render_reference_badge_over_picture():
    source = read(CANVAS / "components/canvas-node.tsx")
    render = source[source.index("return (", source.index("export const CanvasNode")) : source.index("function NodeContent")]
    assert "<ResourceLabelBadge" not in render


def test_canvas_toolbar_centers_in_available_section_after_agent_closes():
    source = read(CANVAS / "[id]/canvas-client-page.tsx")
    toolbar = source[source.index("<CanvasToolbar") : source.index("</section>", source.index("<CanvasToolbar"))]
    assert "zoomControls={<CanvasZoomControls" in toolbar
    assert "leftGutter" not in toolbar


def test_workspace_theme_selector_is_a_single_toggle_button():
    css = read(ROOT / "static/css/site.css")
    options = read(ROOT / "templates/partials/theme_options.html")
    assert 'data-theme-toggle' in options
    assert 'class="theme-menu"' not in options
    assert 'data-theme-option=' not in options
    assert '.rail-theme-toggle .theme-toggle-button' in css


def test_asset_library_has_custom_date_range_and_clean_selection_control():
    template = read(ROOT / "templates/assets.html")
    script = read(ROOT / "static/js/assets.js")
    css = read(ROOT / "static/css/site.css")
    assert "data-filter-date-from" in template
    assert "data-filter-date-to" in template
    assert "matchesDateRange" in script
    assert ".asset-select {" in css and "appearance: none;" in css
    assert ".asset-select:checked::after" in css
    assert ".asset-tile:hover .asset-select-wrap" not in css
    assert ".asset-tile:focus-within .asset-select-wrap" not in css
    assert ".asset-batch-mode .asset-select-wrap" in css
    assert "pointer-events: none;" in css
    assert "pointer-events: auto;" in css
    assert ".asset-select-wrap:has(.asset-select:checked)" not in css


def test_asset_detail_uses_neutral_media_surface_without_black_frame():
    css = read(ROOT / "static/css/site.css")
    assert ".asset-detail-shell .detail-image" in css
    assert "background: var(--color-surface-subtle) !important;" in css


def test_admin_config_navigation_is_nested_in_primary_sidebar_only():
    layout = read(ROOT / "templates/admin/layout.html")
    settings = read(ROOT / "templates/admin/config_settings.html")
    assert "admin-console-config-group" in layout
    assert "配置总览" not in layout
    for label in ("系统配置", "计费规则", "套餐说明"):
        assert label in layout
    assert "admin/_config_sidebar.html" not in settings


def test_audit_filters_are_one_row_with_localized_action_labels():
    template = read(ROOT / "templates/admin/audit.html")
    css = read(ROOT / "static/css/site.css")
    route = read(ROOT / "huishi/routes_admin.py")
    assert "admin-audit-toolbar" in template
    assert "action_labels.get(action, action)" in template
    assert "AUDIT_ACTION_LABELS" in route
    assert ".admin-audit-toolbar" in css and "flex-wrap: nowrap;" in css


def test_settings_summary_uses_readable_solid_product_surfaces():
    css = read(ROOT / "static/css/site.css")
    assert ".admin-console-page .settings-summary article" in css
    assert "background: var(--admin-surface) !important;" in css
    assert "color: var(--admin-ink) !important;" in css


def test_home_hero_keeps_video_bright_and_copy_unframed():
    css = read(ROOT / "static/css/home-tailwind.input.css")
    assert ".home-hero-shade" not in css
    assert ".hero-copy" in css
    assert ".liquid-glass-strong" in css
    assert ".hero-prompt-entry" in css


def test_homepage_uses_real_prompt_entry_and_raf_video_loop():
    source = read(ROOT / "static/js/home.js")
    css = read(ROOT / "static/css/home-tailwind.input.css")
    assert 'const HERO_VIDEO = "/static/media/shouyeshipin-sea.mp4";' in source
    assert 'const CAPABILITIES_VIDEO = "/static/media/huishi-workflow-cloud.mp4";' in source
    assert 'const CAPABILITIES_POSTER = "/static/media/huishi-workflow-cloud-poster.jpg";' in source
    assert 'className={`hero-prompt-entry liquid-glass-strong' in source
    assert "FADE_OUT_LEAD" in source
    assert "requestAnimationFrame" in source
    assert 'className="home-brand-name"' not in source
    assert "<video" in source and " loop" not in source[source.index("<video") : source.index("</video>") if "</video>" in source else source.index("/>", source.index("<video"))]
    assert ".workflow-section" in css and "background: var(--huishi-deep);" in css


def test_admin_link_is_visually_distinct_and_admin_only():
    nav = read(ROOT / "templates/partials/studio_nav.html")
    assert '{% if g.user["role"] == "admin" %}' in nav
    assert 'class="rail-admin-link"' in nav
    assert 'href="/admin/"' in nav
    assert '<span>管理后台</span>' in nav
    assert '<small>管理</small>' not in nav


def test_canvas_agent_batch_reference_upload_keeps_all_images_selected():
    panel = read(CANVAS / "components/canvas-assistant-panel.tsx")
    client = read(CANVAS / "[id]/canvas-client-page.tsx")
    local_panel = read(CANVAS / "components/canvas-local-agent-panel.tsx")
    assert "onPasteImages" in panel
    assert "await onPasteImages(imageFiles)" in panel
    assert "onPasteImages={async (files) =>" in client
    assert "const insertedIds: string[] = []" in client
    assert "setSelectedNodeIds(new Set(insertedIds))" in client
    assert "const MAX_ATTACHMENTS = 8;" in local_panel


def test_workspace_settings_menu_has_one_admin_entry_without_legacy_settings_link():
    studio_nav = read(ROOT / "templates/partials/studio_nav.html")
    canvas_nav = read(ROOT / "templates/partials/canvas_nav.html")
    route = read(ROOT / "huishi/routes_workspace.py")
    assert 'href="/admin/"' in studio_nav
    assert 'href="/admin/"' in canvas_nav
    assert 'href="/settings"' not in studio_nav
    assert 'href="/settings"' not in canvas_nav
    assert 'return redirect(url_for("admin.config_settings"))' in route


def test_public_billing_page_uses_read_only_table_layout_instead_of_cards():
    template = read(ROOT / "templates/pricing.html")
    assert "billing-public-page" in template
    assert "billing-rule-table" in template
    assert "billing-package-list" in template
    assert "pricing-grid" not in template
    assert 'rule["points_per_image"]' in template


def test_admin_settings_final_surface_overrides_status_gradients():
    css = read(ROOT / "static/css/site.css")
    assert ".admin-console-page .settings-summary.settings-health-summary article.is-ok" in css
    assert ".admin-console-page .settings-console-form .settings-section-nav" in css
    final = css.split("/* Admin configuration final surface", 1)[1]
    assert "background: var(--admin-surface) !important;" in final
    assert "backdrop-filter: none !important;" in final
    assert ".admin-console-page.console-page .settings-console-form .provider-list-head strong" in final
    assert ".admin-console-page.console-page .settings-console-form .settings-readiness strong" in final
    assert ".admin-console-page.console-page .settings-console-form .settings-panel-head strong" in final
    assert ".billing-public-page .account-balance-strip strong" in final
    assert "linear-gradient" not in final
