from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator, Iterable

import httpx
from playwright.async_api import async_playwright

from app.config import get_settings
from app.utils.html import extract_main_content, normalize_url

ROBOTS_TXT = "/robots.txt"


async def fetch(session: httpx.AsyncClient, url: str) -> str:
    resp = await session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


async def maybe_render(url: str, html: str) -> str:
    if "<main" in html or not get_settings().playwright_browse:
        return html
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        rendered = await page.content()
        await browser.close()
    return rendered


async def crawl(start_url: str, allowlist: list[str] | None = None, denylist: list[str] | None = None, limit: int = 20) -> AsyncIterator[tuple[str, str, dict[str, str]]]:
    allowlist = allowlist or []
    denylist = denylist or []
    seen: set[str] = set()
    queue = [normalize_url(start_url)]
    async with httpx.AsyncClient(follow_redirects=True) as client:
        while queue and len(seen) < limit:
            url = queue.pop(0)
            if any(pattern in url for pattern in denylist):
                continue
            if allowlist and not any(pattern in url for pattern in allowlist):
                continue
            if url in seen:
                continue
            seen.add(url)
            try:
                html = await fetch(client, url)
                html = await maybe_render(url, html)
            except Exception as exc:  # pragma: no cover
                print(f"crawl error {url}: {exc}")
                continue
            text, meta = extract_main_content(html)
            yield url, text, meta
            for link in re.findall(r"href=\"(https?://[^\"]+)\"", html):
                if link not in seen and len(queue) < limit:
                    queue.append(normalize_url(link))
