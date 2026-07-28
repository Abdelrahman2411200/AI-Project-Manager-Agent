"""Internal isolated Playwright worker for one HTML-to-PDF render."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Route, sync_playwright


def _block_external_request(route: Route) -> None:
    url = route.request.url.casefold()
    if url.startswith(("http:", "https:", "file:", "ftp:", "ws:", "wss:")):
        route.abort()
    else:
        route.continue_()


def render(input_path: Path, output_path: Path) -> None:
    html = input_path.read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-sync",
                "--metrics-recording-only",
                "--no-first-run",
            ],
        )
        try:
            context = browser.new_context(
                accept_downloads=False,
                java_script_enabled=False,
                service_workers="block",
            )
            context.route("**/*", _block_external_request)
            page = context.new_page()
            page.emulate_media(media="print")
            page.set_content(html, wait_until="domcontentloaded")
            output_path.write_bytes(
                page.pdf(
                    format="A4",
                    outline=True,
                    prefer_css_page_size=True,
                    print_background=True,
                    tagged=True,
                )
            )
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    render(arguments.input, arguments.output)


if __name__ == "__main__":
    main()
