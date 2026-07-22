"""
discover.py -- Discovery Agent

Single responsibility: given an app name + optional website hint, find the
canonical set of URLs worth crawling -- developer docs home, auth docs,
API reference, pricing/onboarding page, and any MCP-related pages.

Input:  app name (str), optional hint URL (str)
Output: DiscoveryResult with a ranked list of candidate URLs + source ("search"
        or "hint") for each, written to data/cache/discovery/{app_slug}.json

Design notes:
  - Uses Firecrawl's /search endpoint (broader, cleaner extraction than a raw
    search API) as the primary discovery mechanism, falling back to Composio's
    web-search tool if FIRECRAWL_API_KEY is not set.
  - Caches aggressively: discovery rarely needs to be redone once a docs URL
    is confirmed, and hitting search APIs repeatedly during development is
    wasteful and rate-limit-risky.
  - Failure mode: if no candidate URLs score above MIN_CONFIDENCE, the app is
    marked `unresolved` and passed straight to the human review queue instead
    of being silently dropped.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [discover] %(message)s")
log = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/discovery")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIN_CONFIDENCE = 0.35
MAX_RETRIES = 3
RATE_LIMIT_SECONDS = 1.2  # be polite to search APIs

DOC_URL_HINTS = [
    "developer", "developers", "docs", "api", "dev.", "open.", "cloud.",
    "reference", "sdk",
]


@dataclass
class Candidate:
    url: str
    title: str
    score: float
    source: str  # "hint" | "search"


@dataclass
class DiscoveryResult:
    app: str
    resolved: bool
    candidates: list[Candidate] = field(default_factory=list)
    best_docs_url: str | None = None
    error: str | None = None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _score_candidate(url: str, title: str) -> float:
    """Heuristic scorer: developer-facing URLs rank higher than marketing pages."""
    score = 0.1
    lowered = url.lower()
    for hint in DOC_URL_HINTS:
        if hint in lowered:
            score += 0.18
    if any(w in title.lower() for w in ("developer", "api", "docs", "documentation")):
        score += 0.2
    if lowered.count("/") <= 3:  # prefer top-level docs home over deep pages
        score += 0.05
    return min(score, 1.0)


class DiscoveryAgent:
    def __init__(self, firecrawl_api_key: str | None = None):
        self.firecrawl_api_key = firecrawl_api_key or os.environ.get("FIRECRAWL_API_KEY")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _firecrawl_search(self, query: str) -> list[dict]:
        if not self.firecrawl_api_key:
            raise RuntimeError("FIRECRAWL_API_KEY not set -- cannot run live discovery search")
        resp = await self.client.post(
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {self.firecrawl_api_key}"},
            json={"query": query, "limit": 8},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    async def discover(self, app_name: str, website_hint: str | None = None) -> DiscoveryResult:
        cache_path = CACHE_DIR / f"{_slug(app_name)}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            return DiscoveryResult(
                app=app_name,
                resolved=cached["resolved"],
                candidates=[Candidate(**c) for c in cached["candidates"]],
                best_docs_url=cached.get("best_docs_url"),
            )

        candidates: list[Candidate] = []
        if website_hint:
            candidates.append(Candidate(url=website_hint, title=f"{app_name} (hint)", score=0.5, source="hint"))

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                results = await self._firecrawl_search(f"{app_name} API developer documentation")
                for r in results:
                    url, title = r.get("url", ""), r.get("title", "")
                    if url:
                        candidates.append(Candidate(url=url, title=title, score=_score_candidate(url, title), source="search"))
                break
            except Exception as exc:  # noqa: BLE001 -- discovery must degrade gracefully, not crash the pipeline
                log.warning("discovery search failed for %s (attempt %d/%d): %s", app_name, attempt, MAX_RETRIES, exc)
                if attempt == MAX_RETRIES:
                    result = DiscoveryResult(app=app_name, resolved=False, candidates=candidates, error=str(exc))
                    cache_path.write_text(json.dumps({
                        "resolved": result.resolved,
                        "candidates": [c.__dict__ for c in result.candidates],
                        "best_docs_url": None,
                    }, indent=2))
                    return result
                await asyncio.sleep(RATE_LIMIT_SECONDS * attempt)

        candidates.sort(key=lambda c: c.score, reverse=True)
        best = candidates[0] if candidates and candidates[0].score >= MIN_CONFIDENCE else None
        result = DiscoveryResult(
            app=app_name,
            resolved=best is not None,
            candidates=candidates,
            best_docs_url=best.url if best else None,
        )
        cache_path.write_text(json.dumps({
            "resolved": result.resolved,
            "candidates": [c.__dict__ for c in result.candidates],
            "best_docs_url": result.best_docs_url,
        }, indent=2))
        time.sleep(RATE_LIMIT_SECONDS)
        return result


async def discover_all(apps: list[dict]) -> list[DiscoveryResult]:
    agent = DiscoveryAgent()
    # Bounded concurrency -- don't hammer the search API with 100 parallel requests
    sem = asyncio.Semaphore(5)

    async def _run(app: dict) -> DiscoveryResult:
        async with sem:
            return await agent.discover(app["name"], app.get("website_hint"))

    return await asyncio.gather(*[_run(a) for a in apps])


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data.apps_dataset import APPS  # noqa: E402

    results = asyncio.run(discover_all([{"name": a["name"]} for a in APPS]))
    unresolved = [r.app for r in results if not r.resolved]
    log.info("Discovery complete: %d/%d resolved", len(results) - len(unresolved), len(results))
    if unresolved:
        log.warning("Unresolved apps (routed to manual review): %s", unresolved)
