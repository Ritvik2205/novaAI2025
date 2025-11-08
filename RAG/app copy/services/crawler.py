import asyncio
import hashlib
import logging
from collections import deque
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import xmltodict
from bs4 import BeautifulSoup
from trafilatura import extract as extract_main_content

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CrawledPage:
    url: str
    title: str
    text: str
    raw_html: str
    status_code: int
    last_modified: Optional[str]
    checksum: str


class SiteCrawler:
    """Domain-restricted crawler that extracts cleaned text for indexing."""

    def __init__(
        self,
        base_url: str,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        concurrency: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        self.base_domain = parsed.netloc

        self.max_pages = max_pages or settings.crawler_max_pages
        self.max_depth = max_depth or settings.crawler_max_depth
        self.concurrency = concurrency or settings.crawler_concurrency
        self.timeout = timeout or settings.crawler_timeout

        self.visited: Set[str] = set()
        self.robot_parser = RobotFileParser()

    async def crawl(self) -> List[CrawledPage]:
        await self._load_robot_rules()
        seeds = await self._discover_seed_urls()
        queue = deque((url, 0) for url in seeds)

        pages: List[CrawledPage] = []

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            semaphore = asyncio.Semaphore(self.concurrency)

            async def process(url: str, depth: int) -> None:
                if len(pages) >= self.max_pages:
                    return
                if url in self.visited:
                    return
                self.visited.add(url)

                if not self._robot_allows(url):
                    logger.debug("Skipping %s due to robots.txt", url)
                    return

                try:
                    async with semaphore:
                        response = await client.get(url, headers={"User-Agent": "VentureRAGBot/1.0"})
                except httpx.HTTPError as exc:
                    logger.warning("Failed to fetch %s: %s", url, exc)
                    return

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return

                page = self._build_page(url, response)
                if page:
                    pages.append(page)

                if depth + 1 > self.max_depth:
                    return

                for link in self._extract_links(response.text, url):
                    if len(pages) >= self.max_pages:
                        break
                    queue.append((link, depth + 1))

            while queue and len(pages) < self.max_pages:
                url, depth = queue.popleft()
                await process(url, depth)

        return pages

    async def _discover_seed_urls(self) -> Iterable[str]:
        sitemap_urls = await self._load_sitemap_urls()
        if sitemap_urls:
            return sitemap_urls[: self.max_pages]
        return [self.base_url]

    async def _load_sitemap_urls(self) -> List[str]:
        candidate_paths = ["sitemap.xml", "sitemap_index.xml"]
        urls: List[str] = []

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for candidate in candidate_paths:
                sitemap_url = urljoin(self.base_url + "/", candidate)
                try:
                    response = await client.get(sitemap_url, headers={"User-Agent": "VentureRAGBot/1.0"})
                except httpx.HTTPError:
                    continue
                if response.status_code != httpx.codes.OK:
                    continue

                try:
                    parsed = xmltodict.parse(response.text)
                except Exception as exc:  # pragma: no cover - robustness
                    logger.debug("Failed parsing sitemap %s: %s", sitemap_url, exc)
                    continue

                if "urlset" in parsed:
                    for entry in parsed["urlset"].get("url", []):
                        loc = entry.get("loc")
                        if loc and self._belongs_to_domain(loc):
                            urls.append(loc)
                elif "sitemapindex" in parsed:
                    for entry in parsed["sitemapindex"].get("sitemap", []):
                        loc = entry.get("loc")
                        if not loc:
                            continue
                        urls.extend(await self._load_nested_sitemap(loc))

        return urls

    async def _load_nested_sitemap(self, sitemap_url: str) -> List[str]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                response = await client.get(sitemap_url, headers={"User-Agent": "VentureRAGBot/1.0"})
            except httpx.HTTPError:
                return []
            if response.status_code != httpx.codes.OK:
                return []
            try:
                parsed = xmltodict.parse(response.text)
            except Exception:
                return []

        urls: List[str] = []
        if "urlset" in parsed:
            for entry in parsed["urlset"].get("url", []):
                loc = entry.get("loc")
                if loc and self._belongs_to_domain(loc):
                    urls.append(loc)
        return urls

    async def _load_robot_rules(self) -> None:
        robots_url = urljoin(self.base_url + "/", "robots.txt")
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                response = await client.get(robots_url, headers={"User-Agent": "VentureRAGBot/1.0"})
            except httpx.HTTPError:
                return
        if response.status_code == httpx.codes.OK:
            self.robot_parser.parse(response.text.splitlines())

    def _robot_allows(self, url: str) -> bool:
        try:
            return self.robot_parser.can_fetch("*", url)
        except Exception:
            return True

    def _belongs_to_domain(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == self.base_domain or parsed.netloc.endswith(f".{self.base_domain}")

    def _extract_links(self, html: str, source_url: str) -> Iterable[str]:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            absolute = urljoin(source_url, href)
            if not self._belongs_to_domain(absolute):
                continue
            if absolute in self.visited:
                continue
            if absolute.startswith("mailto:") or absolute.startswith("tel:"):
                continue
            yield absolute.split("#")[0]

    def _build_page(self, url: str, response: httpx.Response) -> Optional[CrawledPage]:
        extracted = extract_main_content(
            response.text,
            url=url,
            include_comments=False,
            favor_recall=True,
            include_images=False,
        )
        if not extracted:
            return None

        soup = BeautifulSoup(response.text, "lxml")
        title_tag = soup.find("title")
        title = title_tag.text.strip() if title_tag else ""

        checksum = hashlib.sha1(extracted.encode("utf-8")).hexdigest()
        last_modified = response.headers.get("last-modified")

        return CrawledPage(
            url=url,
            title=title,
            text=extracted,
            raw_html=response.text,
            status_code=response.status_code,
            last_modified=last_modified,
            checksum=checksum,
        )

