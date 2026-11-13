"""Serve the dashboard locally and capture every tab (for the README and to catch errors).

    python scripts/screenshots.py [OUT_DIR]
"""

from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TABS = ["overview", "targets", "brands", "field", "distribution", "market", "planner"]


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "dashboard"))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(url + "#overview", wait_until="networkidle")
        page.wait_for_timeout(1500)
        for i, tab in enumerate(TABS):
            page.click(f"button[data-tab={tab}]")
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out / f"{i + 1:02d}_{tab}.png"), full_page=True)
        browser.close()
    server.shutdown()
    for e in errors:
        print("ERROR:", e)
    print(f"{len(TABS)} screenshots -> {out}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screens"))
