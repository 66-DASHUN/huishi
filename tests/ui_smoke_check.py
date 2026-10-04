from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("artifacts/ui-smoke")


def main() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        csrf_response = context.request.get(f"{BASE_URL}/api/csrf-token")
        assert csrf_response.ok, csrf_response.text()
        csrf_token = csrf_response.json()["csrf_token"]
        login = context.request.post(
            f"{BASE_URL}/login",
            form={"username": "admin", "password": "1qaz@WSX", "csrf_token": csrf_token},
        )
        assert login.ok, login.text()

        page = context.new_page()
        page.goto(f"{BASE_URL}/admin/config/settings", wait_until="networkidle")
        assert page.title() == "系统配置 - 绘世"
        assert page.locator("#settings-image").count() == 1
        assert page.locator("#settings-storage").count() == 1
        assert page.locator("#settings-runtime").count() == 1
        assert page.locator("button[data-dialog-open='provider-new-image']").count() == 1
        assert page.locator("button[data-dialog-open='provider-new-video']").count() == 1
        assert page.locator("button[data-dialog-open='provider-new-audio']").count() == 1

        page.locator("button[data-dialog-open='provider-new-image']").click()
        image_dialog = page.locator("#provider-new-image")
        assert image_dialog.get_attribute("open") is not None
        assert image_dialog.locator("select[data-model-select] option").count() >= 1
        image_dialog.locator("button[data-dialog-close]").first.click()

        existing_edit = page.locator(
            "button[data-dialog-open^='provider-']:not([data-dialog-open^='provider-new-'])"
        )
        if existing_edit.count():
            edit_id = existing_edit.first.get_attribute("data-dialog-open")
            assert edit_id
            existing_edit.first.click()
            edit_dialog = page.locator(f"#{edit_id}")
            assert edit_dialog.count() == 1
            assert edit_dialog.locator("[data-fetch-models-editor]").count() == 1
            edit_dialog.locator("button[data-dialog-close]").first.click()
            test_button = page.locator("button[data-dialog-open^='test-provider-']").first
            test_id = test_button.get_attribute("data-dialog-open")
            assert test_id
            test_button.click()
            test_dialog = page.locator(f"#{test_id}")
            assert test_dialog.locator("[data-test-model] option").count() >= 1
            assert test_dialog.locator("[data-fetch-models]").count() == 1
            test_dialog.locator("button[data-dialog-close]").first.click()

        page.screenshot(path=str(SCREENSHOT_DIR / "admin-settings.png"), full_page=True)

        workspace = context.new_page()
        workspace.goto(f"{BASE_URL}/workspace", wait_until="networkidle")
        assert workspace.locator("#composer").count() == 1
        assert workspace.locator(".generation-mode-tabs button[data-value='image']").count() == 1
        assert workspace.locator(".generation-mode-tabs button[data-value='video']").count() == 1
        assert workspace.locator(".generation-mode-tabs button[data-value='speech']").count() == 1
        assert workspace.locator(".generation-mode-tabs button[data-value='music']").count() == 1
        assert workspace.locator("#model").count() == 1
        for mode in ("video", "speech", "music", "image"):
            workspace.locator(f".generation-mode-tabs button[data-value='{mode}']").click()
            actual_media_type = workspace.locator("#media-type").input_value()
            print(f"mode={mode} media_type={actual_media_type!r}")
            assert actual_media_type == ("" if mode == "image" else mode)
            assert workspace.locator("#model option").count() >= 1
            if mode == "speech":
                assert workspace.locator("[data-audio-options]").get_attribute("hidden") is None
            if mode == "music":
                assert workspace.locator("[data-music-options]").get_attribute("hidden") is None
        workspace.screenshot(path=str(SCREENSHOT_DIR / "workspace.png"), full_page=True)
        workspace.set_viewport_size({"width": 390, "height": 844})
        workspace.reload(wait_until="networkidle")
        assert workspace.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        workspace.screenshot(path=str(SCREENSHOT_DIR / "workspace-mobile.png"), full_page=True)

        browser.close()


if __name__ == "__main__":
    main()
