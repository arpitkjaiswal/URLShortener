"""Real Chromium regression checks. Run directly from the repository root."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "URL-SHORTNER"
OUTPUT = ROOT / "test-results"
OUTPUT.mkdir(exist_ok=True)


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as directory:
        env = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{directory}/browser.db",
            "BASE_URL": base,
            "PYTHON_DOTENV_DISABLED": "1",
            "CREATE_LIMIT_PER_MINUTE": "100",
            "RENDER": "false",
        }
        with open(OUTPUT / "server.log", "w") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=PROJECT,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(base + "/health", timeout=1):
                            break
                    except OSError:
                        if server.poll() is not None:
                            raise RuntimeError("Test server exited; see test-results/server.log")
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Server did not start")
                exercise_browser(base)
            finally:
                server.terminate()
                server.wait(timeout=10)


def exercise_browser(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100}, permissions=["clipboard-read", "clipboard-write"]
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        expect(page.locator("#list-message")).to_contain_text("Your collection starts here")
        expect(page.locator("#shorten-button")).to_be_disabled()
        # Backend rejects unsupported URLs, and the actual message stays visible.
        page.locator("#url-input").fill("ftp://example.com")
        page.locator("#shorten-button").click()
        expect(page.locator("#form-error")).to_contain_text("valid http(s)")
        page.locator("#url-input").fill("https://example.com/portfolio")
        page.locator("#shorten-button").click()
        expect(page.locator("#result")).to_be_visible()
        expect(page.locator(".link-row")).to_have_count(1)
        short_url = page.locator("#result-link").get_attribute("href")
        code = short_url.rsplit("/", 1)[1]
        page.locator("#copy-result").click()
        assert page.evaluate("navigator.clipboard.readText()") == short_url
        assert context.request.get(short_url, max_redirects=0).status == 307
        page.locator(".stats-link").click()
        expect(page.locator("#stats-modal")).to_be_visible()
        expect(page.locator(".big-clicks")).to_contain_text("1")
        page.keyboard.press("Escape")
        expect(page.locator("#stats-modal")).not_to_be_visible()
        page.reload()
        expect(page.locator(".link-row")).to_have_count(1)
        expect(page.locator("#total-clicks")).to_have_text("1")
        # A separate browser cannot see or delete the first browser's link.
        stranger = browser.new_context()
        stranger_page = stranger.new_page()
        stranger_page.goto(base)
        expect(stranger_page.locator("#list-message")).to_contain_text("Your collection starts here")
        assert stranger.request.delete(base + f"/api/v1/urls/{code}").status == 404
        stranger.close()
        # Payload must be rendered as text, including inside the insights dialog.
        attack = "https://example.com/<img/src=x/onerror=window.xss=1>"
        response = context.request.post(base + "/api/v1/shorten", data={"url": attack})
        assert response.status == 201
        for url in [
            "https://github.com/arpitkjaiswal",
            "https://fastapi.tiangolo.com/",
            "https://render.com/docs",
        ]:
            assert context.request.post(base + "/api/v1/shorten", data={"url": url}).status == 201
        page.locator("#refresh").click()
        expect(page.locator(".link-row")).to_have_count(5)
        assert page.evaluate("window.xss") is None
        assert page.locator(".link-list img").count() == 0
        page.locator("#search").fill("<img")
        expect(page.locator(".link-row")).to_have_count(1)
        page.locator(".stats-link").click()
        expect(page.locator("#stats-body")).to_contain_text(attack)
        assert page.locator("#stats-body img").count() == 0
        page.keyboard.press("Escape")
        page.locator("#search").fill("nonexistent-destination")
        expect(page.locator("#list-message")).to_have_text("No links match your search.")
        page.locator("#search").fill("")
        expect(page.locator(".link-row")).to_have_count(5)
        # Remove the injection fixture before capturing the product screenshot.
        attack_code = response.json()["short_code"]
        assert context.request.delete(base + f"/api/v1/urls/{attack_code}").status == 204
        page.locator("#refresh").click()
        expect(page.locator(".link-row")).to_have_count(4)
        page.screenshot(path=str(OUTPUT / "dashboard-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUTPUT / "dashboard-mobile.png"), full_page=True)
        # Expiry, including owner access to historical stats.
        page.locator("#url-input").fill("https://example.com/temporary")
        page.locator("#ttl-input").fill("1")
        page.locator("#ttl-unit").select_option("1")
        page.locator("#shorten-button").click()
        expect(page.locator(".link-row")).to_have_count(5)
        temporary = page.locator("#result-link").get_attribute("href")
        page.wait_for_timeout(1100)
        assert context.request.get(temporary, max_redirects=0).status == 404
        page.locator("#refresh").click()
        expect(page.locator(".link-status.expired")).to_have_count(1)
        # Cancel and then confirm deletion through the UI.
        row = page.locator(f'[data-short-code="{code}"]')
        row.locator(".delete-link").click()
        page.locator("#cancel-delete").click()
        expect(row).to_be_visible()
        row.locator(".delete-link").click()
        page.locator("#confirm-delete").click()
        expect(row).to_have_count(0)
        assert context.request.get(short_url, max_redirects=0).status == 404
        # Pagination UI must reach links after the first page.
        for i in range(8):
            assert (
                context.request.post(
                    base + "/api/v1/shorten", data={"url": f"https://example.com/page/{i}"}
                ).status
                == 201
            )
        page.locator("#refresh").click()
        expect(page.locator(".link-row")).to_have_count(10)
        page.locator("#next").click()
        expect(page.locator(".link-row")).to_have_count(2)
        page.locator("#previous").click()
        expect(page.locator(".link-row")).to_have_count(10)
        # Fetch failure leaves a retry path, followed by successful recovery.
        page.route("**/api/v1/urls?**", lambda route: route.abort())
        page.locator("#refresh").click()
        expect(page.locator("#list-message")).to_contain_text("Unable to connect")
        page.unroute("**/api/v1/urls?**")
        page.locator("#refresh").click()
        expect(page.locator("#list-message")).not_to_be_visible()
        assert not errors, errors
        browser.close()
    print(
        "Browser checks passed: create, validation, copy, redirects, insights, isolation, XSS, expiry, delete, search, pagination, retry, desktop and mobile layouts."
    )


if __name__ == "__main__":
    main()
