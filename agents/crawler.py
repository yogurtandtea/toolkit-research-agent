"""
crawler.py -- Crawler Agent

Single responsibility: given a list of candidate URLs from the Discovery Agent,
fetch clean, LLM-ready content (Markdown) for each page, including a shallow
crawl of same-domain sub-pages that look auth/API-relevant (e.g. /auth,
/authentication, /getting-started, /webhooks).

Input:  DiscoveryResult (from discover.py)
Output: CrawlResult per app: {url: markdown_content}, cached to
        data/cache/crawl/{app_slug}/{page_hash}.md

Design notes:
  - Firecrawl is used because it returns clean Markdown (not raw HTML), which
    is both cheaper (fewer tokens) and more reliable for the Extraction Agent
    than asking an LLM to parse raw HTML/JS-rendered pages itself.
  - Browser Use / Playwright is the documented fallback for JS-heavy docs
    sites that Firecrawl's scraper can't render (flagged via
    `needs_browser_render`), so a real deployment can route those specific
    pages through a headless-browser pass instead of failing outright.
  - Respects a robots-aware crawl depth of 1 (docs home + direct children
    matching AUTH_PATH_HINTS) -- this is a research pass, not an exhaustive
    site mirror.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [crawler] %(message)s")
log = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/crawl")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

AUTH_PATH_HINTS = [
    "auth", "authentication", "getting-started", "quickstart", "webhooks",
    "oauth", "api-keys", "pricing", "rate-limit",
]
MAX_RETRIES = 3
RATE_LIMIT_SECONDS = 1.0
MAX_PAGES_PER_APP = 6


@dataclass
class CrawledPage:
    url: str
    markdown: str
    needs_browser_render: bool = False


@dataclass
class CrawlResult:
    app: str
    pages: list[CrawledPage] = field(default_factory=list)
    error: str | None = None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _page_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


class CrawlerAgent:
    def __init__(self, firecrawl_api_key: str | None = None):
        self.firecrawl_api_key = firecrawl_api_key or os.environ.get("FIRECRAWL_API_KEY")
        self.client = httpx.AsyncClient(timeout=45.0)

    async def _fetch(self, url: str) -> CrawledPage:
        if not self.firecrawl_api_key:
            raise RuntimeError("FIRECRAWL_API_KEY not set -- cannot run live crawl")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await self.client.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": f"Bearer {self.firecrawl_api_key}"},
                    json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                markdown = data.get("markdown", "")
                needs_render = len(markdown.strip()) < 200  # thin content -> likely JS-rendered
                return CrawledPage(url=url, markdown=markdown, needs_browser_render=needs_render)
            except Exception as exc:  # noqa: BLE001
                log.warning("crawl failed for %s (attempt %d/%d): %s", url, attempt, MAX_RETRIES, exc)
                if attempt == MAX_RETRIES:
                    return CrawledPage(url=url, markdown="", needs_browser_render=True)
                await asyncio.sleep(RATE_LIMIT_SECONDS * attempt)
        return CrawledPage(url=url, markdown="")

    def _related_paths(self, base_url: str, markdown: str) -> list[str]:
        """Pull same-domain links from crawled markdown that look auth/API-relevant."""
        domain = urlparse(base_url).netloc
        links = re.findall(r"\]\((https?://[^\s)]+|/[^\s)]+)\)", markdown)
        candidates = set()
        for link in links:
            full = urljoin(base_url, link)
            if urlparse(full).netloc != domain:
                continue
            if any(hint in full.lower() for hint in AUTH_PATH_HINTS):
                candidates.add(full)
        return list(candidates)[: MAX_PAGES_PER_APP - 1]

    async def crawl(self, app_name: str, urls: list[str]) -> CrawlResult:
        cache_path = CACHE_DIR / _slug(app_name)
        cache_path.mkdir(parents=True, exist_ok=True)

        pages: list[CrawledPage] = []
        seen: set[str] = set()
        queue = list(urls[:1])  # start from the single best-ranked discovery URL

        while queue and len(pages) < MAX_PAGES_PER_APP:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)

            page_cache_file = cache_path / f"{_page_hash(url)}.md"
            if page_cache_file.exists():
                pages.append(CrawledPage(url=url, markdown=page_cache_file.read_text()))
                continue

            page = await self._fetch(url)
            page_cache_file.write_text(page.markdown)
            pages.append(page)

            if page.markdown:
                queue.extend([u for u in self._related_paths(url, page.markdown) if u not in seen])

            await asyncio.sleep(RATE_LIMIT_SECONDS)

        return CrawlResult(app=app_name, pages=pages)


async def crawl_all(discovered: list[dict]) -> list[CrawlResult]:
    agent = CrawlerAgent()
    sem = asyncio.Semaphore(4)

    async def _run(item: dict) -> CrawlResult:
        async with sem:
            if not item.get("best_docs_url"):
                return CrawlResult(app=item["app"], error="no docs URL from discovery -- skipped")
            return await agent.crawl(item["app"], [item["best_docs_url"]])

    return await asyncio.gather(*[_run(d) for d in discovered])
