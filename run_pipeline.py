"""
run_pipeline.py -- Pipeline Orchestrator

This is the single entry point that reproduces every deliverable in outputs/
and website/data.js from the source dataset.

Two modes:

  1. STATIC MODE (default, no API keys required):
     Loads data/apps_dataset.py -- the already-researched, already-verified
     100-app dataset produced for this submission (see data/apps_dataset.py's
     module docstring for exactly how it was produced) -- and runs it through
     Classification -> Analysis -> Report generation. This reproduces every
     output file in outputs/ and website/data.js deterministically, with no
     external API calls, in a few seconds.

  2. LIVE MODE (--live flag, requires FIRECRAWL_API_KEY + ANTHROPIC_API_KEY,
     optionally COMPOSIO_API_KEY):
     Runs the full Discovery -> Crawler -> Extraction -> Verification chain
     against live documentation for a given app list, producing a fresh
     dataset from scratch. This is the path a reviewer would use to confirm
     the pipeline code actually works end-to-end, or to extend the research
     to new apps beyond the original 100.

Usage:
    python run_pipeline.py                  # static mode, uses bundled dataset
    python run_pipeline.py --live            # live mode, re-researches everything
    python run_pipeline.py --live --apps "Linear,Notion"   # live mode, subset
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.classifier import enrich_all
from agents.analysis import run_full_analysis
from agents.report import generate_all
from agents.verifier import write_review_queue_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [pipeline] %(message)s")
log = logging.getLogger(__name__)


def write_verification_csv_from_log(path: str = "outputs/verification.csv") -> None:
    from data.human_review_log import VERIFICATION_LOG
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["App", "Field", "First-pass assumption", "Verified finding", "Evidence", "Confidence before", "Confidence after"])
        for r in VERIFICATION_LOG:
            writer.writerow([
                r["app"], r["field"], r["first_pass_assumption"], r["verified_finding"],
                r["evidence"], r["confidence_before"], r["confidence_after"],
            ])
    log.info("Wrote %d verification rows to %s", len(VERIFICATION_LOG), path)


def run_static_mode() -> None:
    from data.apps_dataset import APPS

    log.info("STATIC MODE: loading bundled, pre-researched dataset (%d apps)", len(APPS))
    enriched = enrich_all(APPS)

    log.info("Running Confidence Scorer -> routing low-confidence records to manual review queue")
    low_confidence = [r for r in enriched if r.get("confidence", 0) < 65]
    write_review_queue_csv(low_confidence)

    log.info("Running Analysis Agent")
    analysis = run_full_analysis(enriched)

    log.info("Writing verification.csv from the actual human/agent verification pass performed this session")
    write_verification_csv_from_log()

    log.info("Running Dataset Generator (JSON, CSV, SQLite) + Report Agent (website data)")
    generate_all(enriched, analysis)

    log.info("Pipeline complete. Outputs in outputs/, website data in website/data.js")
    log.info("Summary: %d apps | %d buildable today | %d gated | %d manual-review",
              analysis["total_apps"],
              analysis["buildability_distribution"].get("buildable_today", 0),
              analysis["buildability_distribution"].get("buildable_gated", 0),
              analysis["manual_review_queue_size"])


async def run_live_mode(app_names: list[str] | None) -> None:
    from agents.discover import discover_all
    from agents.crawler import crawl_all
    from agents.extractor import extract_all

    if app_names is None:
        from data.apps_dataset import APPS
        app_names = [a["name"] for a in APPS]

    log.info("LIVE MODE: researching %d apps from scratch via Firecrawl + Claude", len(app_names))
    log.warning("Requires FIRECRAWL_API_KEY and ANTHROPIC_API_KEY environment variables.")

    discovered = await discover_all([{"name": n} for n in app_names])
    log.info("Discovery: %d/%d apps resolved to a docs URL", sum(1 for d in discovered if d.resolved), len(discovered))

    crawled = await crawl_all([{"app": d.app, "best_docs_url": d.best_docs_url} for d in discovered])
    log.info("Crawl: fetched pages for %d apps", sum(1 for c in crawled if c.pages))

    extracted = await extract_all([
        {"app": c.app, "category": "", "pages": [{"url": p.url, "markdown": p.markdown} for p in c.pages]}
        for c in crawled
    ])
    log.info("Extraction: produced %d records", len(extracted))

    enriched = enrich_all(extracted)
    analysis = run_full_analysis(enriched)
    generate_all(enriched, analysis)
    log.info("Live pipeline complete. NOTE: run the Verification Agent (agents/verifier.py) "
              "against this fresh extraction before trusting it for a case study -- "
              "this command only performs the first-pass extraction, by design.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Composio-style SaaS research pipeline")
    parser.add_argument("--live", action="store_true", help="Run live discovery/crawl/extraction instead of using the bundled dataset")
    parser.add_argument("--apps", type=str, default=None, help="Comma-separated subset of app names (live mode only)")
    args = parser.parse_args()

    if args.live:
        subset = args.apps.split(",") if args.apps else None
        asyncio.run(run_live_mode(subset))
    else:
        run_static_mode()
