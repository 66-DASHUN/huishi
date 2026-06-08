def test_user_can_register_login_and_view_account(client):
    response = client.post(
        "/register",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "alice" in response.get_data(as_text=True)

    client.get("/logout")

    response = client.post(
        "/login",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "账户中心" in response.get_data(as_text=True)
    assert "account-summary" in response.get_data(as_text=True)
    assert "ledger-list" in response.get_data(as_text=True)


def test_user_can_register_login_with_email_and_verify(client, app, monkeypatch):
    sent_messages = []

    def fake_send_verification_email(email, code):
        sent_messages.append((email, code))

    monkeypatch.setattr("huishi.auth.send_verification_email", fake_send_verification_email)

    response = client.post(
        "/register",
        data={"email": "alice@example.com", "username": "alice_email", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify-email")

    with app.app_context():
        from huishi.db import get_db

        user = get_db().execute("SELECT * FROM users WHERE email = ?", ("alice@example.com",)).fetchone()
        code = user["email_verification_token"]
    assert user["email_verified"] == 0
    assert code and len(code) == 6
    assert sent_messages == [("alice@example.com", code)]

    client.get("/logout")
    response = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "alice_email" in response.get_data(as_text=True)

    verify_page = client.get("/verify-email")
    assert verify_page.status_code == 200
    verify_text = verify_page.get_data(as_text=True)
    assert "alice@example.com" in verify_text
    assert "autocomplete=\"one-time-code\"" in verify_text
    assert code not in verify_text

    response = client.post("/verify-email", data={"code": code}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        from huishi.db import get_db

        verified = get_db().execute("SELECT email_verified FROM users WHERE email = ?", ("alice@example.com",)).fetchone()
    assert verified["email_verified"] == 1


def test_email_verification_rejects_wrong_code(client, monkeypatch):
    monkeypatch.setattr("huishi.auth.send_verification_email", lambda email, code: None)

    client.post(
        "/register",
        data={"email": "wrongcode@example.com", "username": "wrongcode", "password": "secret123"},
        follow_redirects=True,
    )

    response = client.post("/verify-email", data={"code": "000000"})

    assert response.status_code == 400


def test_email_registration_reports_when_email_cannot_be_sent(client, monkeypatch):
    def fail_send(email, code):
        raise RuntimeError("SMTP not configured")

    monkeypatch.setattr("huishi.auth.send_verification_email", fail_send)

    response = client.post(
        "/register",
        data={"email": "nosend@example.com", "username": "nosend", "password": "secret123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "验证码发送失败" in response.get_data(as_text=True)


def test_register_respects_safe_next_destination(client):
    response = client.post(
        "/register?next=/workspace",
        data={"username": "nextuser", "password": "secret123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workspace")


def test_full_login_page_copy_matches_homepage_return_flow(client):
    response = client.get("/login?next=/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "登录后留在首页" in text
    assert "进入工作台、资产库和积分账户" not in text
    assert 'href="/register?next=/"' in text


def test_full_register_page_copy_matches_homepage_return_flow(client):
    response = client.get("/register?next=/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "注册后返回首页" in text
    assert "自动进入工作台" not in text
    assert 'href="/login?next=/"' in text


def test_register_next_does_not_redirect_to_external_site(client):
    response = client.post(
        "/register?next=https://evil.example/phish",
        data={"username": "safeuser", "password": "secret123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account")


def test_admin_account_shows_management_entry(client):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    response = client.get("/account")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "管理后台" in text
    assert "/admin/" in text


def test_workspace_requires_login(client):
    response = client.get("/workspace", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_logged_in_user_can_view_workspace(client):
    client.post("/register", data={"username": "carol", "password": "secret123"}, follow_redirects=True)
    response = client.get("/workspace")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "你好，想创作什么？" in text
    assert "开启创作" in text
    assert "新对话" in text
    assert "默认创作" not in text
    assert "最近" not in text
    assert "Ref" not in text
    assert "预计消耗" not in text
    assert "点" in text
    assert "AR" not in text
    assert "高清 2K" not in text
    assert 'name="ratio" id="ratio" value="16:9"' in text
    assert 'id="ratio-label">16:9' in text
    assert 'id="custom-width"' in text
    assert 'id="custom-height"' in text
    assert 'id="estimate">2 点' in text
    assert "资产" in text
    assert "composer-controls" in text
    assert "prompt-meta" in text
    assert "0 / 1000" in text
    assert "生成作品" in text
    assert "generate-icon" in text
    assert "generate-text" in text
    assert "Base URL" not in text
    assert "API Key" not in text


def test_empty_workspace_uses_centered_creation_card(client):
    client.post("/register", data={"username": "empty-studio", "password": "secret123"}, follow_redirects=True)
    response = client.get("/workspace")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "empty-creation-stage" in text
    assert "empty-composer-card" in text
    assert "你好，想创作什么？" in text
    assert "资产" in text
    assert "studio-filterbar" not in text
    assert "生成后的图片会显示在这里" not in text


def test_workspace_new_creation_keeps_existing_records_but_opens_empty_composer(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "new-chat-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'new-chat-user'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '已有作品', '/static/uploads/existing.png', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/workspace?new=1").get_data(as_text=True)

    assert "empty-composer-card" in text
    assert "你好，想创作什么？" in text
    assert "已有作品" in text
    assert "creation-item" not in text
    assert 'href="/workspace?new=1"' in text


def test_workspace_keeps_asset_filtering_out_of_creation_flow(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "filter-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'filter-user'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '筛选作品', '/static/uploads/filter.png', 'reference', '9:16', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/workspace").get_data(as_text=True)

    assert "filter-menu" not in text
    assert "data-workspace-search" not in text
    assert "data-workspace-sort" not in text
    assert "data-workspace-mode" not in text
    assert "data-scroll-composer" not in text
    assert "操作类型" not in text
    assert "<summary>生成模式</summary>" not in text
    assert 'data-record-mode="reference"' in text


def test_workspace_and_assets_share_clean_studio_navigation(client):
    client.post("/register", data={"username": "sharednav", "password": "secret123"}, follow_redirects=True)

    workspace = client.get("/workspace").get_data(as_text=True)
    assets = client.get("/assets").get_data(as_text=True)

    for text in (workspace, assets):
        assert 'aria-label="主导航"' in text
        assert "生成" in text
        assert "资产" in text
        assert "充值" in text
        assert "账号" in text
        assert "新对话" in text
        assert 'conversation-thumb">+</span>' not in text
        assert "灵感" not in text
        assert "会员" not in text
        assert "默认创作" not in text
        assert "work-folder-list" not in text
        assert "/history" not in text


def test_regular_user_settings_menu_hides_admin_entries(client):
    client.post("/register", data={"username": "regular-menu", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "账号" in text
    assert "充值" in text
    assert "黑色主题" in text or "白色主题" in text
    assert "/admin/" not in text
    assert "/settings" not in text
    assert ">管理<" not in text
    assert ">设置<" not in text


def test_admin_navigation_shows_management_and_settings(client):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "管理" in text
    assert "设置" in text
    assert "/settings" in text


def test_workspace_shows_records_as_creation_flow_without_thumbnail_strip(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "studio-records", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'studio-records'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '主视觉图', '/static/uploads/main.png', 'text', '2K', '2560x1440', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '最近缩略图', '/static/uploads/recent.png', 'reference', '1K', '864x1536', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    response = client.get("/workspace")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "主视觉图" in text
    assert "最近缩略图" in text
    assert "recent-strip" not in text
    assert "recent-card" not in text
    assert "重新编辑" in text
    assert "再次生成" in text
    assert "查看参数" in text


def test_workspace_renders_history_dialogues_and_clean_new_dialogue(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "dialogue-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'dialogue-user'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '第一条历史对话提示词很长很长', '/static/uploads/dialogue.png', 'text', '9:16', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    workspace = client.get("/workspace").get_data(as_text=True)
    new_dialogue = client.get("/workspace?new=1").get_data(as_text=True)

    assert "历史对话" in workspace
    assert "第一条历史对话" in workspace
    assert "你好，想创作什么？" in new_dialogue
    assert "输入提示词，选择生成模式" not in new_dialogue
    assert "creation-item" not in new_dialogue


def test_workspace_result_toolbar_places_meta_on_action_row(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "toolbar-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'toolbar-user'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '工具栏布局', '/static/uploads/toolbar.png', 'text', '9:16', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/workspace").get_data(as_text=True)

    assert "creation-toolbar" in text
    assert "creation-action-group" in text
    assert "creation-meta" in text
    assert "<span>9:16</span>" in text
    assert "<span>2K</span>" in text
    assert "<span>1440x2560</span>" in text
    assert "<span>2 pts</span>" in text
    assert "图片生成</span>" not in text
    assert text.index("creation-action-group") < text.index("creation-meta")


def test_generated_workspace_uses_output_state_contract(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "output-state", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'output-state'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '生成后作品态测试', '/static/uploads/output.png', 'text', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/workspace").get_data(as_text=True)
    assert "creation-stream" in text
    assert "creation-toolbar" in text
    assert "creation-action-group" in text
    assert "重新编辑" in text
    assert "再次生成" in text
    assert 'class="creation-prompt" title="生成后作品态测试"' in text
    assert "output-composer" in text
    assert "empty-composer-card" not in text


def test_workspace_parameter_popover_contains_dimensions(client):
    client.post("/register", data={"username": "popover-user", "password": "secret123"}, follow_redirects=True)
    text = client.get("/workspace").get_data(as_text=True)

    assert "parameter-popover" in text
    assert 'aria-controls="ratio-panel"' in text
    assert 'aria-expanded="false"' in text
    assert "选择比例" in text
    assert "选择分辨率" not in text
    assert 'id="custom-width"' in text
    assert 'id="custom-height"' in text
    assert 'name="width"' in text
    assert 'name="height"' in text
    assert 'data-value="4:3"' in text
    assert 'data-value="3:4"' in text


def test_workspace_uses_reference_upload_instead_of_manual_mode_tabs(client):
    client.post("/register", data={"username": "reference-chip-user", "password": "secret123"}, follow_redirects=True)
    text = client.get("/workspace").get_data(as_text=True)

    assert "reference-chip" not in text
    assert ">Ref<" not in text
    assert 'id="reference-images"' in text
    assert "reference-input" in text
    assert "data-reference-add" in text
    assert "count-stepper" in text
    assert 'title="生成数量"' in text
    assert 'data-count-step="-1"' in text
    assert 'data-count-step="1"' in text
    assert "size-pill" not in text
    assert "reference-material-stack" in text
    assert "dimension-inline" in text
    assert 'data-field="mode"' not in text


def test_workspace_uses_material_stack_not_reference_upload_copy(client):
    client.post("/register", data={"username": "material-stack-user", "password": "secret123"}, follow_redirects=True)

    response = client.get("/workspace")
    text = response.get_data(as_text=True)

    assert 'class="reference-material-stack' in text
    assert 'data-reference-stack' in text
    assert 'data-reference-add' in text
    assert 'id="reference-preview"' in text
    assert 'data-reference-list' in text
    assert 'id="reference-preview-modal"' in text
    assert 'data-close-reference-preview' in text
    assert 'name="reference_images"' in text
    assert 'name="reference_paths"' in text
    assert "参考图上传" not in text
    assert "图生图" not in text


def test_reference_material_entry_lives_inside_prompt_shell_not_control_row(client):
    client.post("/register", data={"username": "reference-entry-position", "password": "secret123"}, follow_redirects=True)

    response = client.get("/workspace")
    text = response.get_data(as_text=True)
    prompt_shell_start = text.index('class="composer-prompt-shell"')
    prompt_shell_end = text.index('<input type="hidden" name="csrf_token"', prompt_shell_start)
    prompt_shell_markup = text[prompt_shell_start:prompt_shell_end]
    controls_start = text.index('class="composer-controls"')
    controls_end = text.index('<div class="parameter-popover"', controls_start)
    controls_markup = text[controls_start:controls_end]

    assert 'data-reference-stack' in prompt_shell_markup
    assert 'data-reference-add' in prompt_shell_markup
    assert 'data-reference-stack' not in controls_markup


def test_workspace_rendered_images_are_draggable_reference_sources(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "drag-source-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = ?", ("drag-source-user",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, image_paths, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'drag source', '/static/uploads/drag-source.png', '["/static/uploads/drag-source.png"]', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/workspace").get_data(as_text=True)

    assert 'draggable="true"' in text
    assert 'data-reference-path="/static/uploads/drag-source.png"' in text


def test_home_page_is_still_available(client):
    response = client.get("/")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "绘世" in text
    assert "/assets/" in text or "进入工作台" in text or "工作台" in text


def test_asset_detail_uses_theme_preview_without_local_theme_toggle(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "detail-preview", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'detail-preview'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '详情预览', '/static/uploads/detail.png', 'text', '16:9', '2K', '2560x1440', 'auto', 'png', 1, 'demo', 1.2, 2, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get(f"/assets/{cursor.lastrowid}?from=workspace&next=/workspace").get_data(as_text=True)

    assert "image-preview-modal" in text
    assert 'data-preview-src="/static/uploads/detail.png"' in text
    assert "data-theme-toggle" not in text
    assert "返回工作区" in text


def test_workspace_contains_prompt_optimization_controls(client):
    client.post("/register", data={"username": "prompt-ui", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "优化提示词" in text
    assert 'class="optimize-button"' in text
    assert 'id="prompt-style"' not in text
    assert "写实摄影" not in text
    assert "prompt-optimize-modal" not in text


def test_workspace_composer_controls_can_wrap_before_overlapping():
    from pathlib import Path
    import re

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    desktop_controls = re.search(r"^\.composer-controls \{([^}]*)\}", stylesheet, re.MULTILINE).group(1)

    assert "flex-wrap: wrap" in desktop_controls
    assert "grid-template-columns: auto auto auto auto auto minmax(130px, 1fr) 148px" not in desktop_controls
    assert re.search(r"\.workspace-page \.composer \.optimize-button \{[^}]*flex: 0 1 132px", stylesheet)
    assert ".dimension-inline .custom-dim-input" in stylesheet


def test_reference_material_stack_expands_without_reflowing_controls():
    from pathlib import Path
    import re

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    expanded_stack = re.search(
        r"^\.reference-material-stack:hover,\n\.reference-material-stack\.is-expanded \{([^}]*)\}",
        stylesheet,
        re.MULTILINE,
    ).group(1)
    expanded_list = re.search(
        r"^\.reference-material-stack:hover \.reference-material-list,\n"
        r"\.reference-material-stack\.is-expanded \.reference-material-list \{([^}]*)\}",
        stylesheet,
        re.MULTILINE,
    ).group(1)
    expanded_tiles = re.search(
        r"^\.reference-material-stack:hover \.reference-material-tile,\n"
        r"\.reference-material-stack\.is-expanded \.reference-material-tile \{([^}]*)\}",
        stylesheet,
        re.MULTILINE,
    ).group(1)

    assert "width: 64px" in expanded_stack
    assert "width: min(292px, 42vw)" not in expanded_stack
    assert "position: absolute" in expanded_list
    assert "position: relative" not in expanded_tiles


def test_reference_material_stack_uses_compact_overlapping_cards():
    from pathlib import Path
    import re

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    stack_rule = re.search(r"^\.reference-material-stack \{([^}]*)\}", stylesheet, re.MULTILINE).group(1)
    card_rule = re.search(
        r"^\.reference-add-card,\n\.reference-material-tile \{([^}]*)\}",
        stylesheet,
        re.MULTILINE,
    ).group(1)
    material_add_rule = re.search(
        r"^\.reference-material-stack\.has-materials \.reference-add-card \{([^}]*)\}",
        stylesheet,
        re.MULTILINE,
    ).group(1)

    assert "width: 64px" in stack_rule
    assert "min-width: 64px" in stack_rule
    assert "height: 64px" in stack_rule
    assert "width: 44px" in card_rule
    assert "height: 56px" in card_rule
    assert "width: 26px" in material_add_rule
    assert "height: 26px" in material_add_rule


def test_reference_material_stack_is_anchored_inside_prompt_area():
    from pathlib import Path
    import re

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    prompt_rule = re.search(r"^\.composer-prompt \{([^}]*)\}", stylesheet, re.MULTILINE).group(1)
    stack_rule = re.search(r"^\.reference-material-stack \{([^}]*)\}", stylesheet, re.MULTILINE).group(1)

    assert "padding: 8px 80px 8px 76px" in prompt_rule
    assert "position: absolute" in stack_rule
    assert "left: 12px" in stack_rule
    assert "top: 12px" in stack_rule


def test_reference_material_remove_control_is_not_nested_in_tile_button():
    from pathlib import Path

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")

    assert 'document.createElement("button")' in script
    assert 'const tile = document.createElement("button")' not in script
    assert 'const remove = document.createElement("button")' in script
    assert 'remove.setAttribute("role", "button")' not in script


def test_reference_material_keyboard_preview_does_not_intercept_remove_button():
    from pathlib import Path
    import re

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")
    keydown_handler = re.search(
        r'referencePreview\?\.addEventListener\("keydown", \(event\) => \{(?P<body>[\s\S]*?)\n  \}\);',
        script,
    ).group("body")

    assert 'event.target.closest(".reference-remove")' in keydown_handler
    assert 'if (event.target.closest(".reference-remove")) return;' in keydown_handler


def test_reference_material_stack_collapses_when_empty():
    from pathlib import Path
    import re

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")
    render_function = re.search(
        r"function renderReferenceMaterials\(\) \{(?P<body>[\s\S]*?)\n\}",
        script,
    ).group("body")

    assert "hasReference" in render_function
    assert 'referenceStack?.classList.remove("is-expanded")' in render_function


def test_reference_material_remove_button_resets_native_button_chrome():
    from pathlib import Path
    import re

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    remove_rule = re.search(r"^\.reference-remove \{([^}]*)\}", stylesheet, re.MULTILINE).group(1)

    assert "border: 0" in remove_rule
    assert "padding: 0" in remove_rule
    assert "cursor: pointer" in remove_rule


def test_custom_dimension_inputs_have_room_for_four_digit_sizes():
    from pathlib import Path
    import re

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    dimension_rule = re.search(
        r"^\.workspace-page \.composer \.dimension-inline \{([^}]*)\}",
        stylesheet,
        re.MULTILINE,
    ).group(1)
    input_rule = re.search(r"^\.dimension-inline \.custom-dim-input \{([^}]*)\}", stylesheet, re.MULTILINE).group(1)

    assert "flex: 0 0 164px" in dimension_rule
    assert "flex: 0 0 62px" in input_rule
    assert "width: 62px" in input_rule
    assert "height: 24px" in input_rule
    assert "line-height: 24px" in input_rule


def test_mobile_material_stack_keeps_same_compact_anchor():
    from pathlib import Path

    stylesheet = Path("static/css/site.css").read_text(encoding="utf-8")
    mobile_section = stylesheet[stylesheet.index("@media (max-width: 760px)") :]

    assert ".composer-prompt { min-height: 100px; resize: none; padding: 16px 72px 34px 76px;" in mobile_section
    assert ".reference-material-stack { width: 64px; min-width: 64px; }" in mobile_section
    assert ".reference-material-stack:hover { width: 64px; }" in mobile_section


def test_workspace_edit_seed_restores_reference_material_paths():
    from pathlib import Path
    import re

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")
    seed_function = re.search(
        r"function applySeedToComposer\(seed\) \{(?P<body>[\s\S]*?)\n\}",
        script,
    ).group("body")

    assert "seed.reference_paths" in seed_function
    assert "addReferencePath" in seed_function
    assert "clearReferenceImages" in seed_function


def test_output_composer_does_not_auto_collapse_when_editing_reference_seed():
    from pathlib import Path
    import re

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")
    keep_open_function = re.search(
        r"function shouldKeepComposerExpanded\(\) \{(?P<body>[\s\S]*?)\n\}",
        script,
    ).group("body")
    collapse_function = re.search(
        r"function bindComposerCollapse\(\) \{(?P<body>[\s\S]*?)\n\}",
        script,
    ).group("body")

    assert "getEditSeed()" in keep_open_function
    assert "referenceMaterials.length" in keep_open_function
    assert "form?.classList.contains(\"has-reference\")" in keep_open_function
    assert "!shouldKeepComposerExpanded()" in collapse_function
    assert "setComposerCollapsed(false)" in collapse_function


def test_reference_material_preview_treats_hovered_stack_as_expanded():
    from pathlib import Path
    import re

    script = Path("static/js/workspace.js").read_text(encoding="utf-8")
    helper_function = re.search(
        r"  function isReferenceStackExpanded\(\) \{(?P<body>[\s\S]*?)\n  \}",
        script,
    ).group("body")
    click_block = re.search(
        r"referencePreview\?\.addEventListener\(\"click\", \(event\) => \{(?P<body>[\s\S]*?)\n  \}\);",
        script,
    ).group("body")

    assert "matches(\":hover\")" in helper_function
    assert "isReferenceStackExpanded()" in click_block


def test_workspace_contains_generation_task_region(client):
    client.post("/register", data={"username": "taskregion", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert 'id="generation-task-region"' in text
    assert "generation-task-card" in text


def test_workspace_failure_task_template_includes_prompt_and_parameters(client):
    client.post("/register", data={"username": "failure-template", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "data-task-failure-prompt" in text
    assert "data-task-failure-params" in text
    assert "data-task-failure-cost" in text


def test_generate_accepts_existing_reference_paths_without_reupload(client, app, monkeypatch):
    from huishi.db import get_db

    client.post("/register", data={"username": "existing-ref-user", "password": "secret123"}, follow_redirects=True)
    calls = {}

    def fake_generate_image(**kwargs):
        calls["mode"] = kwargs["mode"]
        references = kwargs["reference_images"]
        calls["reference_names"] = [item.filename for item in references]
        calls["reference_bytes"] = [item.read() for item in references]
        return {
            "image_path": "/static/uploads/generated-existing-ref.png",
            "image_paths": ["/static/uploads/generated-existing-ref.png"],
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", ("existing-ref-user",)).fetchone()
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user["id"],))
        output_dir = app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "source-ref.png").write_bytes(b"existing-reference")
        db.commit()

    response = client.post(
        "/generate",
        data={
            "prompt": "use existing reference",
            "ratio": "16:9",
            "width": "1536",
            "height": "864",
            "count": "1",
            "reference_paths": "/static/uploads/source-ref.png",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["record"]["mode"] == "reference"
    assert payload["record"]["reference_paths"] == ["/static/uploads/source-ref.png"]
    assert calls["mode"] == "reference"
    assert calls["reference_names"] == ["source-ref.png"]
    assert calls["reference_bytes"] == [b"existing-reference"]


def test_workspace_related_pages_use_global_theme_controls(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "theme-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'theme-user'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '主题测试', '/static/uploads/theme.png', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    for path in ("/workspace", "/assets"):
        text = client.get(path).get_data(as_text=True)
        assert "data-theme-toggle" in text
        assert "js/theme.js" in text

    detail_text = client.get(f"/assets/{record_id}").get_data(as_text=True)
    assert "data-theme-toggle" not in detail_text
    assert "js/theme.js" in detail_text


def test_workspace_contains_points_and_regenerate_modals(client):
    client.post("/register", data={"username": "modaluser", "password": "secret123"}, follow_redirects=True)

    text = client.get("/workspace").get_data(as_text=True)

    assert "points-shortage-modal" in text
    assert "regenerate-confirm-modal" in text
    assert "去充值" in text
    assert "不再提示" in text


def test_history_route_is_not_an_asset_entry(client):
    client.post("/register", data={"username": "nohistory", "password": "secret123"}, follow_redirects=True)

    response = client.get("/history")

    assert response.status_code == 404


def test_regular_user_cannot_access_settings(client):
    client.post("/register", data={"username": "nosettings", "password": "secret123"}, follow_redirects=True)

    response = client.get("/settings")

    assert response.status_code == 403


def test_assets_page_lists_user_records(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "assetlistuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'assetlistuser'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '资产图像', '/static/uploads/demo.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
    response = client.get("/assets")
    assert response.status_code == 200
    assert "资产图像" in response.get_data(as_text=True)


def test_assets_page_renders_image_only_asset_library(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "assetuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'assetuser'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '资产库图像', '/static/uploads/asset.png', 'text', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, 1, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    text = client.get("/assets").get_data(as_text=True)
    assert "asset-library" in text
    assert "图片资产" in text
    assert "全部图片" in text
    assert "我的收藏" in text
    assert "筛选" in text
    assert "批量操作" in text
    assert "asset-thumb" in text
    assert "asset-card-body" in text
    assert "asset-select-wrap" in text
    assert "data-filter-open" in text
    assert "data-batch-toggle" in text
    assert 'data-mode="text"' in text
    assert 'data-ratio="16:9"' in text
    assert "资产库图像" in text
    assert "璧勪骇" not in text
    assert "绛涢" not in text
    assert "鎵归" not in text
    assert "鈱" not in text
    assert "超清" not in text
    assert 'data-asset-filter="2K"' not in text
    assert "视频" not in text
    assert "音频" not in text
    assert "文档" not in text
    assert "无限画布" not in text
    assert "同步剪映" not in text


def test_bulk_favorite_and_delete_assets(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "bulkuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'bulkuser'").fetchone()["id"]
        for prompt in ("批量一", "批量二"):
            db.execute(
                """
                INSERT INTO records
                (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
                VALUES (?, ?, '/static/uploads/bulk.png', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
                """,
                (user_id, prompt, utc_now()),
            )
        db.commit()

    favorite = client.post(
        "/assets/bulk/favorite",
        json={"ids": [1, 2], "favorite": True},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert favorite.status_code == 200
    assert favorite.get_json()["updated"] == 2

    delete = client.post(
        "/assets/bulk/delete",
        json={"ids": [1, 2]},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert delete.status_code == 200
    assert delete.get_json()["deleted"] == 2


def test_assets_page_contains_filter_drawer_and_batch_controls(client):
    client.post("/register", data={"username": "filter-ui", "password": "secret123"}, follow_redirects=True)

    text = client.get("/assets").get_data(as_text=True)

    assert "asset-filter-drawer" in text
    assert 'aria-controls="asset-filter-drawer"' in text
    assert 'aria-expanded="false"' in text
    assert "data-filter-mode" in text
    assert "data-filter-ratio" in text
    assert "data-batch-toggle" in text
    assert 'aria-pressed="false"' in text
    assert "data-bulk-download" in text
    assert "data-batch-clear" in text
    assert "data-asset-empty" in text


def test_bulk_download_returns_zip_for_owned_assets(client, app, tmp_path):
    from huishi.db import get_db, utc_now

    upload_dir = app.config["OUTPUT_DIR"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "zip-a.png").write_bytes(b"image-a")
    (upload_dir / "zip-b.png").write_bytes(b"image-b")

    client.post("/register", data={"username": "zipuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'zipuser'").fetchone()["id"]
        for filename in ("zip-a.png", "zip-b.png"):
            db.execute(
                """
                INSERT INTO records
                (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
                VALUES (?, ?, ?, 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
                """,
                (user_id, filename, f"/static/uploads/{filename}", utc_now()),
            )
        db.commit()

    response = client.post(
        "/assets/bulk/download",
        json={"ids": [1, 2]},
        headers={"X-Requested-With": "fetch", "Accept": "application/zip"},
    )

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.data.startswith(b"PK")


def test_workspace_edit_record_prefills_original_prompt_and_parameters(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "editseed", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'editseed'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '继续编辑这张图', '/static/uploads/editseed.png', 'reference', '3:2', '2K', '2160x1440', 'high', 'webp', 2, 'demo', 1.2, 4, '["/static/uploads/ref-edit.png"]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    response = client.get(f"/workspace?edit_record={record_id}")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-edit-seed=' in text
    assert "继续编辑这张图" in text
    assert '"mode": "reference"' in text
    assert '"ratio": "3:2"' in text
    assert '"resolution": "2K"' in text
    assert '"quality": "high"' in text
    assert '"output_format": "webp"' in text
    assert '"count": 2' in text
    assert "/static/uploads/ref-edit.png" in text
    assert ">继续编辑这张图</textarea>" in text
    assert 'name="mode" id="mode" value="reference"' in text
    assert 'name="ratio" id="ratio" value="3:2"' in text
    assert 'name="width" id="width"' in text
    assert 'name="height" id="height"' in text
    assert 'id="custom-width"' in text
    assert 'id="custom-height"' in text
    assert 'name="quality" id="quality" value="high"' in text
    assert 'name="output_format" id="output-format" value="webp"' in text
    assert 'name="count" type="number" min="1" max="8" value="2"' in text


def test_workspace_edit_record_rejects_invalid_or_unowned_record(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "edit-owner", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        owner_id = db.execute("SELECT id FROM users WHERE username = 'edit-owner'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'owned edit seed', '/static/uploads/owned-edit.png', 'text', '16:9', '1K', '1536x864', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (owner_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    assert client.get("/workspace?edit_record=not-a-number").status_code == 404

    client.get("/logout")
    client.post("/register", data={"username": "edit-other", "password": "secret123"}, follow_redirects=True)

    assert client.get(f"/workspace?edit_record={record_id}").status_code == 404


def test_assets_page_links_to_workspace_edit_record_without_nested_anchor(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "asset-edit-link", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'asset-edit-link'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'asset edit entry', '/static/uploads/asset-edit-entry.png', 'text', '9:16', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    text = client.get("/assets").get_data(as_text=True)

    assert f'href="/workspace?edit_record={record_id}"' in text
    assert "asset-edit-action" in text
    assert "再次编辑" in text
    assert '<a class="asset-tile"' not in text
    assert '<article class="asset-tile"' in text


def test_records_store_ratio_and_reference_paths(client, app):
    from huishi.records import create_record, get_record_for_user
    from huishi.db import get_db

    client.post("/register", data={"username": "ratio-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'ratio-user'").fetchone()["id"]
        record_id = create_record(
            user_id=user_id,
            prompt="ratio prompt",
            image_path="/static/uploads/ratio.png",
            mode="text",
            ratio="9:16",
            resolution="2K",
            actual_size="1440x2560",
            quality="auto",
            output_format="png",
            count=1,
            model_source="test",
            elapsed_seconds=0.2,
            points_charged=2,
            reference_paths=["/static/uploads/ref-a.png"],
        )
        db.commit()
        record = get_record_for_user(record_id, user_id)

    assert record["ratio"] == "9:16"
    assert "/static/uploads/ref-a.png" in record["reference_paths"]


def test_app_settings_table_exists(client, app):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    with app.app_context():
        from huishi.db import get_db

        get_db().execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('prompt_model', 'gpt-4.1-mini', '2026-06-04T00:00:00+00:00')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """
        )
        saved = get_db().execute("SELECT value FROM app_settings WHERE key = 'prompt_model'").fetchone()

    assert saved["value"] == "gpt-4.1-mini"


def test_settings_page_saves_api_config(client):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    response = client.post(
        "/settings",
        data={"base_url": "https://example.com/v1", "api_key": "sk-user"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "设置已保存" in text
    assert "https://example.com/v1" in text
    assert "sk-user" not in text


def test_settings_page_saves_global_image_api_config(client, app):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)

    response = client.post(
        "/settings",
        data={"base_url": "https://global.example/v1", "api_key": "sk-global"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        from huishi.db import get_db

        rows = {
            row["key"]: row["value"]
            for row in get_db().execute(
                "SELECT key, value FROM app_settings WHERE key IN ('image_base_url', 'image_api_key')"
            ).fetchall()
        }
    assert rows == {"image_base_url": "https://global.example/v1", "image_api_key": "sk-global"}


def test_settings_rejects_non_http_base_url(client):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    response = client.post(
        "/settings",
        data={"base_url": "javascript:alert(1)", "api_key": "sk-user"},
    )

    assert response.status_code == 400


def test_settings_page_keeps_existing_global_api_key_when_field_left_blank(client, app):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    client.post(
        "/settings",
        data={"base_url": "https://example.com/v1", "api_key": "sk-original"},
        follow_redirects=True,
    )
    client.post(
        "/settings",
        data={"base_url": "https://example.com/v1", "api_key": ""},
        follow_redirects=True,
    )

    with app.app_context():
        from huishi.db import get_db

        saved = get_db().execute("SELECT value FROM app_settings WHERE key = 'image_api_key'").fetchone()

    assert saved["value"] == "sk-original"


def test_global_image_api_config_is_used_for_regular_user_generation(client, monkeypatch):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    client.post(
        "/settings",
        data={"base_url": "https://global.example/v1", "api_key": "sk-global"},
        follow_redirects=True,
    )
    client.get("/logout")
    client.post("/register", data={"username": "globalgen", "password": "secret123"}, follow_redirects=True)

    calls = {}

    def fake_generate_image(**kwargs):
        calls["api_key"] = kwargs["api_key"]
        calls["base_url"] = kwargs["base_url"]
        return {
            "image_path": "/static/uploads/keep.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        "/generate",
        data={"prompt": "保留密钥", "mode": "text", "ratio": "16:9", "resolution": "1K", "count": "1"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    assert response.status_code == 200
    assert calls["api_key"] == "sk-global"
    assert calls["base_url"] == "https://global.example/v1"


def test_admin_can_save_prompt_optimization_settings(client, app):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)

    response = client.post(
        "/settings",
        data={
            "base_url": "https://image.example/v1",
            "api_key": "sk-image",
            "prompt_base_url": "https://text.example/v1",
            "prompt_api_key": "sk-text",
            "prompt_model": "gpt-4.1-mini",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Prompt 优化" in text
    assert "https://text.example/v1" in text
    assert "sk-text" not in text

    with app.app_context():
        from huishi.db import get_db

        rows = {row["key"]: row["value"] for row in get_db().execute("SELECT key, value FROM app_settings").fetchall()}
    assert rows["prompt_base_url"] == "https://text.example/v1"
    assert rows["prompt_api_key"] == "sk-text"
    assert rows["prompt_model"] == "gpt-4.1-mini"


def test_prompt_optimize_reports_when_not_configured(client):
    client.post("/register", data={"username": "optuser", "password": "secret123"}, follow_redirects=True)

    response = client.post(
        "/api/prompt/optimize",
        json={"prompt": "一只猫", "style": "通用增强"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "暂未启用 Prompt 优化" in response.get_json()["error"]


def test_prompt_optimize_calls_configured_provider(client, app, monkeypatch):
    client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    client.post(
        "/settings",
        data={
            "base_url": "https://image.example/v1",
            "api_key": "sk-image",
            "prompt_base_url": "https://text.example/v1",
            "prompt_api_key": "sk-text",
            "prompt_model": "gpt-4.1-mini",
        },
        follow_redirects=True,
    )
    client.get("/logout")
    client.post("/register", data={"username": "optcall", "password": "secret123"}, follow_redirects=True)

    calls = {}

    def fake_optimize_prompt(**kwargs):
        calls.update(kwargs)
        return "优化后的猫，柔和光线，细腻毛发"

    monkeypatch.setattr("huishi.routes_workspace.optimize_prompt", fake_optimize_prompt)
    response = client.post(
        "/api/prompt/optimize",
        json={"prompt": "一只猫", "style": "写实摄影"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json()["optimized_prompt"] == "优化后的猫，柔和光线，细腻毛发"
    assert calls["prompt"] == "一只猫"
    assert calls["style"] == "写实摄影"
    assert calls["api_key"] == "sk-text"
    assert calls["base_url"] == "https://text.example/v1"
    assert calls["model"] == "gpt-4.1-mini"


def test_prompt_optimize_accepts_string_provider_response(monkeypatch):
    from huishi import prompt_api

    class FakeCompletions:
        def create(self, **kwargs):
            return "优化后的东方女孩，柔和光线，细腻肤色"

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(prompt_api, "OpenAI", FakeClient)

    result = prompt_api.optimize_prompt(
        prompt="一个东方女孩",
        style="通用",
        api_key="sk-text",
        base_url="https://text.example/v1",
        model="gpt-4.1-mini",
    )

    assert result == "优化后的东方女孩，柔和光线，细腻肤色"


def test_asset_detail_uses_asset_route_and_full_metadata(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "asset-detail-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'asset-detail-user'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'asset detail prompt', '/static/uploads/detail.png', 'text', '1:1', '2K', '2048x2048', 'auto', 'png', 1, 'demo', 1.2, 2, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    response = client.get(f"/assets/{record_id}")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "asset detail prompt" in text
    assert "1:1" in text
    assert "2K" in text
    assert "2048x2048" in text
    assert "png" in text
    assert "1.2" in text
    assert "再次编辑" in text
    assert "再次生成" in text
    assert "返回资产库" in text
    assert "下载" in text
    assert "/assets" in text
    assert f"/assets/{record_id}/favorite" in text
    assert f"/assets/{record_id}/delete" in text


def test_asset_detail_return_url_preserves_origin_path(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "asset-return-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'asset-return-user'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'return detail prompt', '/static/uploads/return.png', 'text', '9:16', '2K', '1440x2560', 'auto', 'png', 1, 'demo', 1.2, 2, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    text = client.get(f"/assets/{record_id}?next=/workspace?dialogue=12%23latest").get_data(as_text=True)

    assert 'href="/workspace?dialogue=12#latest"' in text
    assert "返回工作区" in text


def test_old_image_detail_route_is_not_public_entry(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "old-image-route", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'old-image-route'").fetchone()["id"]
        db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'old detail route', '/static/uploads/old.png', 'text', '16:9', '1K', '1536x864', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()

    assert client.get("/image/1").status_code == 404


def test_asset_detail_requires_record_owner(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "owner", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        owner_id = db.execute("SELECT id FROM users WHERE username = 'owner'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '测试提示词', '/static/uploads/demo.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (owner_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid
    response = client.get(f"/assets/{record_id}")
    assert response.status_code == 200
    assert "测试提示词" in response.get_data(as_text=True)

    client.get("/logout")
    client.post("/register", data={"username": "other", "password": "secret123"}, follow_redirects=True)
    response = client.get(f"/assets/{record_id}")
    assert response.status_code == 404


def test_asset_regenerate_creates_new_record_after_balance_check(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "regenuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'regenuser'").fetchone()["id"]
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user_id,))
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '再次生成提示词', '/static/uploads/original.png', 'text', '16:9', '1K', '1536x864', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    calls = []

    def fake_generate_image(**kwargs):
        calls.append(kwargs)
        assert kwargs["prompt"] == "再次生成提示词"
        assert kwargs["mode"] == "text"
        assert kwargs["ratio"] == "16:9"
        assert kwargs["resolution"] == "1K"
        assert kwargs["count"] == 1
        assert kwargs["quality"] == "auto"
        assert kwargs["output_format"] == "png"
        assert kwargs["reference_images"] == []
        return {
            "image_path": "/static/uploads/regenerated.png",
            "actual_size": "1536x864",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        f"/assets/{record_id}/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["record"]["id"] != record_id
    assert payload["record"]["prompt"] == "再次生成提示词"
    assert payload["record"]["image_path"] == "/static/uploads/regenerated.png"
    assert payload["balance"] == 19
    assert len(calls) == 1
    with app.app_context():
        db = get_db()
        rows = db.execute("SELECT * FROM records WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

    assert len(rows) == 2
    assert rows[-1]["points_charged"] == 1
    assert user["points"] == 19


def test_asset_regenerate_refuses_reference_without_saved_sources(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "oldrefregen", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'oldrefregen'").fetchone()["id"]
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user_id,))
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '旧参考图', '/static/uploads/ref.png', 'reference', '9:16', '1K', '864x1536', 'auto', 'png', 1, 'demo', 1.2, 2, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    monkeypatch.setattr(
        "huishi.routes_workspace.generate_image",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call API")),
    )
    response = client.post(
        f"/assets/{record_id}/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "重新上传参考图" in response.get_json()["error"]
    with app.app_context():
        db = get_db()
        record_count = db.execute("SELECT COUNT(*) AS count FROM records WHERE user_id = ?", (user_id,)).fetchone()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

    assert record_count["count"] == 1
    assert user["points"] == 20


def test_asset_regenerate_reuses_saved_reference_sources(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "savedrefregen", "password": "secret123"}, follow_redirects=True)
    source_bytes = b"\x89PNG\r\n\x1a\nsaved-reference"
    with app.app_context():
        upload_dir = app.config["OUTPUT_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "saved-ref.png").write_bytes(source_bytes)
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'savedrefregen'").fetchone()["id"]
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user_id,))
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'saved reference prompt', '/static/uploads/ref-original.png', 'reference', '9:16', '1K', '864x1536', 'auto', 'png', 1, 'demo', 1.2, 2, '["/static/uploads/saved-ref.png"]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    calls = {}

    def fake_generate_image(**kwargs):
        references = kwargs["reference_images"]
        calls["mode"] = kwargs["mode"]
        calls["reference_name"] = references[0].filename
        calls["reference_bytes"] = references[0].read()
        return {
            "image_path": "/static/uploads/regenerated-ref.png",
            "actual_size": "864x1536",
            "model_source": "fake",
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr("huishi.routes_workspace.generate_image", fake_generate_image)
    response = client.post(
        f"/assets/{record_id}/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["record"]["mode"] == "reference"
    assert calls == {
        "mode": "reference",
        "reference_name": "saved-ref.png",
        "reference_bytes": source_bytes,
    }
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()
        new_record = db.execute("SELECT * FROM records WHERE id = ?", (payload["record"]["id"],)).fetchone()

    assert user["points"] == 19
    assert "/static/uploads/saved-ref.png" in new_record["reference_paths"]


def test_asset_regenerate_refuses_reference_when_saved_source_file_is_missing(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "missingrefregen", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'missingrefregen'").fetchone()["id"]
        db.execute("UPDATE users SET points = 20 WHERE id = ?", (user_id,))
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'missing reference prompt', '/static/uploads/ref-original.png', 'reference', '9:16', '1K', '864x1536', 'auto', 'png', 1, 'demo', 1.2, 2, '["/static/uploads/missing-ref.png"]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    monkeypatch.setattr(
        "huishi.routes_workspace.generate_image",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call API")),
    )
    response = client.post(
        f"/assets/{record_id}/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "源文件不存在" in response.get_json()["error"]
    with app.app_context():
        db = get_db()
        record_count = db.execute("SELECT COUNT(*) AS count FROM records WHERE user_id = ?", (user_id,)).fetchone()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

    assert record_count["count"] == 1
    assert user["points"] == 20


def test_asset_regenerate_requires_balance_before_calling_api(client, app, monkeypatch):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "regenpoor", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'regenpoor'").fetchone()["id"]
        db.execute("UPDATE users SET points = 0 WHERE id = ?", (user_id,))
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, '余额不足再生成', '/static/uploads/poor.png', 'text', '16:9', '1K', '1536x864', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    monkeypatch.setattr(
        "huishi.routes_workspace.generate_image",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call API")),
    )
    response = client.post(
        f"/assets/{record_id}/regenerate",
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "积分" in response.get_json()["error"]
    with app.app_context():
        db = get_db()
        record_count = db.execute("SELECT COUNT(*) AS count FROM records WHERE user_id = ?", (user_id,)).fetchone()
        user = db.execute("SELECT points FROM users WHERE id = ?", (user_id,)).fetchone()

    assert record_count["count"] == 1
    assert user["points"] == 0


def test_record_favorite_and_delete(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "detailuser", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'detailuser'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, '可操作记录', '/static/uploads/demo.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    response = client.post(f"/assets/{record_id}/favorite", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/assets/{record_id}")

    response = client.get(f"/assets/{record_id}")
    assert response.status_code == 200
    assert "取消收藏" in response.get_data(as_text=True)

    response = client.post(f"/assets/{record_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "可操作记录" not in response.get_data(as_text=True)


def test_asset_delete_hides_record_but_keeps_file_and_reference_history(client, app):
    client.post("/register", data={"username": "soft-delete-user", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        from huishi.db import get_db, utc_now

        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", ("soft-delete-user",)).fetchone()
        output_dir = app.config["OUTPUT_DIR"]
        output_dir.mkdir(parents=True, exist_ok=True)
        image_file = output_dir / "soft-delete.png"
        image_file.write_bytes(b"image")
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, image_paths, mode, ratio, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, reference_paths, favorite, created_at)
            VALUES (?, 'soft delete source', '/static/uploads/soft-delete.png', '["/static/uploads/soft-delete.png"]', 'text', '1:1', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, '[]', 0, ?)
            """,
            (user["id"], utc_now()),
        )
        record_id = cursor.lastrowid
        db.commit()

    response = client.post(f"/assets/{record_id}/delete", follow_redirects=False)

    assert response.status_code in {302, 200}
    with app.app_context():
        from huishi.db import get_db

        db = get_db()
        row = db.execute("SELECT hidden FROM records WHERE id = ?", (record_id,)).fetchone()
        assert row is not None
        assert row["hidden"] == 1
        assert (app.config["OUTPUT_DIR"] / "soft-delete.png").exists()


def test_asset_mutating_actions_require_record_owner(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "asset-action-owner", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        owner_id = db.execute("SELECT id FROM users WHERE username = 'asset-action-owner'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, 'protected action record', '/static/uploads/protected.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (owner_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    client.get("/logout")
    client.post("/register", data={"username": "asset-action-other", "password": "secret123"}, follow_redirects=True)

    favorite_response = client.post(f"/assets/{record_id}/favorite")
    delete_response = client.post(f"/assets/{record_id}/delete")

    assert favorite_response.status_code == 404
    assert delete_response.status_code == 404
    with app.app_context():
        record = get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()

    assert record is not None
    assert record["user_id"] == owner_id
    assert record["favorite"] == 0
    assert record["prompt"] == "protected action record"


def test_asset_actions_return_json_for_fetch_requests(client, app):
    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "asset-json-actions", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        owner_id = db.execute("SELECT id FROM users WHERE username = 'asset-json-actions'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, 'json action record', '/static/uploads/json-actions.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (owner_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    headers = {"X-Requested-With": "fetch", "Accept": "application/json"}
    favorite_response = client.post(f"/assets/{record_id}/favorite", headers=headers)

    assert favorite_response.status_code == 200
    assert favorite_response.get_json() == {"ok": True, "favorite": 1}

    delete_response = client.post(f"/assets/{record_id}/delete", headers=headers)

    assert delete_response.status_code == 200
    assert delete_response.get_json() == {"ok": True}
    with app.app_context():
        record = get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()

    assert record is not None
    assert record["hidden"] == 1


def test_delete_record_keeps_local_uploaded_file(client, app):
    from pathlib import Path

    from huishi.db import get_db, utc_now

    client.post("/register", data={"username": "filedelete", "password": "secret123"}, follow_redirects=True)
    with app.app_context():
        upload_dir = Path(app.config["OUTPUT_DIR"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        image_file = upload_dir / "owned.png"
        image_file.write_bytes(b"image")
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = 'filedelete'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO records
            (user_id, prompt, image_path, mode, resolution, actual_size, quality, output_format, count, model_source, elapsed_seconds, points_charged, favorite, created_at)
            VALUES (?, 'delete file', '/static/uploads/owned.png', 'text', '1K', '1024x1024', 'auto', 'png', 1, 'demo', 1.2, 1, 0, ?)
            """,
            (user_id, utc_now()),
        )
        db.commit()
        record_id = cursor.lastrowid

    response = client.post(f"/assets/{record_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/assets")
    assert image_file.exists()
    with app.app_context():
        record = get_db().execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    assert record is not None
    assert record["hidden"] == 1
