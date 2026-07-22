"""
report.py -- Dataset Generator + Report Agent

Single responsibility: take the final, enriched, verified records + analysis
output and materialize every deliverable format the assignment asks for:
  - outputs/dataset.json   (full structured records)
  - outputs/dataset.csv    (flat, spreadsheet-friendly)
  - outputs/dataset.db     (SQLite, queryable)
  - outputs/analysis.json  (distributions + insights, consumed by the HTML page)
  - website/data.js        (dataset + analysis embedded as a JS global, so the
                             static HTML case study has no server dependency)

This agent does not decide what the numbers are (analysis.py already did that);
it only serializes them consistently across formats so a reviewer can open
whichever one they trust most and get the same story.
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [report] %(message)s")
log = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs")
WEBSITE_DIR = Path("website")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WEBSITE_DIR.mkdir(parents=True, exist_ok=True)

CSV_FIELDS = [
    "name", "category", "description", "authentication", "selfServe", "apiTypes",
    "webhooks", "graphql", "soap", "mcpSupport", "toolkitVerdict", "blocker",
    "confidence", "evidence", "notes", "buildability_tier", "gate_type", "auth_primary",
]


def write_json(records: list[dict], path: str = "outputs/dataset.json") -> None:
    Path(path).write_text(json.dumps(records, indent=2))
    log.info("Wrote %d records to %s", len(records), path)


def write_csv(records: list[dict], path: str = "outputs/dataset.csv") -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = dict(r)
            for list_field in ("authentication", "apiTypes", "evidence"):
                row[list_field] = "; ".join(row.get(list_field) or [])
            writer.writerow(row)
    log.info("Wrote %d records to %s", len(records), path)


def write_sqlite(records: list[dict], path: str = "outputs/dataset.db") -> None:
    Path(path).unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE apps (
            name TEXT PRIMARY KEY,
            category TEXT,
            description TEXT,
            authentication TEXT,
            self_serve TEXT,
            api_types TEXT,
            webhooks INTEGER,
            graphql INTEGER,
            soap INTEGER,
            mcp_support TEXT,
            toolkit_verdict TEXT,
            blocker TEXT,
            confidence INTEGER,
            evidence TEXT,
            notes TEXT,
            buildability_tier TEXT,
            gate_type TEXT,
            auth_primary TEXT
        )
    """)
    for r in records:
        cur.execute(
            "INSERT INTO apps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                r["name"], r["category"], r.get("description", ""),
                "; ".join(r.get("authentication") or []), r.get("selfServe", ""),
                "; ".join(r.get("apiTypes") or []),
                int(bool(r.get("webhooks"))) if r.get("webhooks") is not None else None,
                int(bool(r.get("graphql"))), int(bool(r.get("soap"))),
                r.get("mcpSupport", ""), r.get("toolkitVerdict", ""), r.get("blocker", ""),
                r.get("confidence", 0), "; ".join(r.get("evidence") or []), r.get("notes", ""),
                r.get("buildability_tier", ""), r.get("gate_type", ""), r.get("auth_primary", ""),
            ),
        )
    conn.commit()
    conn.close()
    log.info("Wrote %d records to SQLite at %s", len(records), path)


def write_analysis(analysis: dict, path: str = "outputs/analysis.json") -> None:
    Path(path).write_text(json.dumps(analysis, indent=2))
    log.info("Wrote analysis summary to %s", path)


def write_website_data(records: list[dict], analysis: dict, path: str = "website/data.js") -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data.human_review_log import VERIFICATION_LOG, summary  # noqa: E402

    payload = (
        f"window.APPS_DATA = {json.dumps(records, indent=2)};\n"
        f"window.ANALYSIS_DATA = {json.dumps(analysis, indent=2)};\n"
        f"window.VERIFICATION_LOG = {json.dumps(VERIFICATION_LOG, indent=2)};\n"
        f"window.VERIFICATION_SUMMARY = {json.dumps(summary(), indent=2)};\n"
    )
    Path(path).write_text(payload)
    log.info("Wrote embedded dataset + analysis + verification log to %s", path)


def generate_all(records: list[dict], analysis: dict) -> None:
    write_json(records)
    write_csv(records)
    write_sqlite(records)
    write_analysis(analysis)
    write_website_data(records, analysis)
