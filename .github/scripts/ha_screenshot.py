#!/usr/bin/env python3
"""Take a screenshot of a Home Assistant dashboard view.

Usage:
    python .github/scripts/ha_screenshot.py [view_path] [--out FILE] [--width W] [--height H]

Examples:
    python .github/scripts/ha_screenshot.py yaml-domov/7
    python .github/scripts/ha_screenshot.py yaml-domov/7 --out car.png

Credentials are read from .env in the repo root (HA_URL, HA_USERNAME, HA_PASSWORD).
Auth state is cached to .tmp/ha_storage_state.json for reuse. No credentials are printed.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"
TMP_DIR = REPO_ROOT / ".tmp"
STATE_FILE = TMP_DIR / "ha_storage_state.json"


def load_env():
    """Read .env file and return dict of key=value pairs."""
    if not ENV_FILE.exists():
        print(f"ERROR: .env file not found at {ENV_FILE}", file=sys.stderr)
        sys.exit(1)
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def login_and_save_state(ha_url, username, password, playwright):
    """Log in via the HA UI and save storageState for reuse."""
    TMP_DIR.mkdir(exist_ok=True)
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(color_scheme="dark")
    page = context.new_page()

    print("Logging in to HA ...")
    page.goto(ha_url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    # HA uses Shadow DOM — Playwright locators pierce it by default
    page.get_by_role("textbox").first.fill(username)
    page.locator("input[type='password']").fill(password)
    page.get_by_role("button", name="Log in").click()

    # Wait for dashboard to load
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")

    # Verify we're not still on login
    if "/auth/" in page.url:
        print(f"ERROR: Login failed — still on {page.url}", file=sys.stderr)
        page.screenshot(path=str(TMP_DIR / "screenshot-login-debug.png"))
        browser.close()
        sys.exit(1)

    # Save the auth state
    context.storage_state(path=str(STATE_FILE))
    print(f"Auth state saved to {STATE_FILE.name}")

    browser.close()


def main():
    parser = argparse.ArgumentParser(description="Screenshot an HA dashboard view")
    parser.add_argument(
        "view", nargs="?", default="yaml-domov/7", help="Dashboard/view path"
    )
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument("--width", type=int, default=1280, help="Viewport width")
    parser.add_argument("--height", type=int, default=2400, help="Viewport height")
    parser.add_argument(
        "--relogin", action="store_true", help="Force re-login even if state exists"
    )
    args = parser.parse_args()

    env = load_env()
    ha_url = env.get("HA_URL", "http://homeassistant.local:8123")
    username = env.get("HA_USERNAME")
    password = env.get("HA_PASSWORD")
    if not username or not password:
        print(
            "ERROR: HA_USERNAME and HA_PASSWORD required in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    TMP_DIR.mkdir(exist_ok=True)
    out_path = args.out or str(
        TMP_DIR / f"screenshot-{args.view.replace('/', '-')}.png"
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # Login if no saved state or --relogin
        if args.relogin or not STATE_FILE.exists():
            login_and_save_state(ha_url, username, password, p)

        # Open browser with saved auth state
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            color_scheme="dark",
            storage_state=str(STATE_FILE),
        )
        page = context.new_page()

        url = f"{ha_url}/{args.view}"
        print(f"Navigating to {url} ...")
        page.goto(url, wait_until="networkidle", timeout=30000)

        # Check if we ended up on the login page (state expired)
        if "/auth/" in page.url or "auth_callback" in page.url:
            print("Session expired, re-logging in ...")
            browser.close()
            login_and_save_state(ha_url, username, password, p)

            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": args.width, "height": args.height},
                color_scheme="dark",
                storage_state=str(STATE_FILE),
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

        # Wait for cards to render
        page.wait_for_timeout(6000)

        page.screenshot(path=out_path, full_page=True)
        print(f"Screenshot saved to {out_path}")

        browser.close()

    return out_path


if __name__ == "__main__":
    main()
