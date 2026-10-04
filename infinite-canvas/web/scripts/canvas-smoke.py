from pathlib import Path
from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path(".canvas-smoke")
    output.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, width, height in (("desktop", 1440, 900), ("mobile", 390, 844)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto("http://127.0.0.1:3000/canvas", wait_until="networkidle")
            page.screenshot(path=str(output / f"{name}.png"), full_page=True)
            print(name, page.url)
            print("workspace", page.locator("[data-canvas-workspace-shell]").count())
            print("side_tools", page.locator("[data-canvas-side-tools]").count())
            print("mobile_toolbar", page.locator("[data-canvas-mobile-toolbar]").count())
            print("horizontal_overflow", page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
