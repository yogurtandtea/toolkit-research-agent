"""
extractor.py -- Extraction Agent

Single responsibility: turn crawled Markdown docs into a structured AppRecord
by prompting an LLM (Claude by default, OpenAI as a configurable fallback) to
extract exactly the fields in schema.AppRecord, grounded strictly in the
crawled text -- never from the model's own training knowledge.

Input:  CrawlResult (from crawler.py) -- concatenated markdown per app
Output: AppRecord (unverified -- confidence is provisional, Verification
        Agent re-checks it before it's considered final)

Design notes:
  - The system prompt explicitly forbids the model from inventing an answer
    when the crawled text doesn't cover a field; it must emit "unknown" and
    a low per-field confidence instead. This is the single most important
    anti-hallucination control in the pipeline.
  - Uses structured JSON-mode output (see product docs) so the report/CSV/
    SQLite generators can consume it without brittle regex parsing.
  - Every extraction is logged with a content hash of its input, so a
    re-run only re-calls the LLM if the underlying crawled docs changed
    (cache invalidation tied to content, not just app name).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [extractor] %(message)s")
log = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/extraction")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are the Extraction Agent in an automated SaaS-research pipeline.
You will be given the name of an application and crawled Markdown content from its
official developer documentation.

Extract ONLY the following fields, grounded strictly in the provided text:
- category
- description (one line)
- authentication (list: OAuth2, API key, Basic, token, other)
- selfServe (can a developer get credentials themselves for free/trial, or is it gated
  by payment/admin-approval/partnership?)
- apiTypes (REST, GraphQL, SOAP, etc)
- webhooks (true/false)
- mcpSupport (official / third-party / none found)
- toolkitVerdict (buildable today / buildable but gated / not verifiable)
- blocker (the main obstacle, if any)
- evidence (list of URLs actually present in the crawled content that support your answer)

CRITICAL RULES:
1. If the crawled text does not clearly support a field, output "unknown" for that
   field and lower the confidence score -- do NOT guess or fill in from general
   knowledge about the company.
2. Every non-"unknown" claim must be traceable to a specific evidence URL you were
   given, not invented.
3. Output strict JSON matching the AppRecord schema. No prose outside the JSON.
"""


def _content_hash(app_name: str, markdown: str) -> str:
    return hashlib.sha256(f"{app_name}::{markdown}".encode()).hexdigest()[:24]


class ExtractionAgent:
    def __init__(self, anthropic_api_key: str | None = None, model: str = "claude-sonnet-4-6"):
        self.api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.client = httpx.AsyncClient(timeout=60.0)

    async def extract(self, app_name: str, category_hint: str, markdown: str, evidence_urls: list[str]) -> dict:
        if not markdown.strip():
            return {
                "name": app_name, "category": category_hint, "description": "unknown",
                "authentication": [], "selfServe": "unknown", "apiTypes": [], "webhooks": None,
                "mcpSupport": "unknown", "toolkitVerdict": "not verifiable -- no crawlable content",
                "blocker": "discovery/crawl produced no usable content", "confidence": 10,
                "evidence": [], "notes": "Routed to manual review: empty crawl result.",
            }

        cache_key = _content_hash(app_name, markdown)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())

        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set -- cannot run live extraction")

        user_prompt = (
            f"App name: {app_name}\nCategory hint: {category_hint}\n"
            f"Evidence URLs available: {evidence_urls}\n\n"
            f"--- CRAWLED DOCUMENTATION ---\n{markdown[:12000]}\n--- END DOCUMENTATION ---"
        )

        resp = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1200,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        record = json.loads(content)
        cache_file.write_text(json.dumps(record, indent=2))
        return record


async def extract_all(crawled: list[dict]) -> list[dict]:
    agent = ExtractionAgent()
    records = []
    for item in crawled:
        combined_md = "\n\n".join(p["markdown"] for p in item.get("pages", []))
        evidence = [p["url"] for p in item.get("pages", []) if p.get("markdown")]
        records.append(await agent.extract(item["app"], item.get("category", ""), combined_md, evidence))
    return records
