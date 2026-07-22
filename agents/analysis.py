"""
analysis.py -- Insight Generation

Single responsibility: turn the enriched, verified dataset into the
distributions, cross-tabs, and headline observations the case study leads with.
This module deliberately does NOT touch presentation (no HTML/Chart.js here) --
report.py consumes its output. Keeping analysis separate from rendering means
the same numbers can be reused in the CSV/README summary and the HTML charts
without recomputing (or worse, hand-typing them twice and having them drift).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict


def distribution(records: list[dict], field: str) -> dict[str, int]:
    counter = Counter()
    for r in records:
        val = r.get(field)
        if isinstance(val, list):
            for v in val:
                counter[v] += 1
        else:
            counter[val or "unknown"] += 1
    return dict(counter.most_common())


def cross_tab(records: list[dict], row_field: str, col_field: str) -> dict:
    table = defaultdict(lambda: defaultdict(int))
    for r in records:
        table[r.get(row_field, "unknown")][r.get(col_field, "unknown")] += 1
    return {k: dict(v) for k, v in table.items()}


def category_ease_ranking(records: list[dict]) -> list[dict]:
    """Rank categories by share of apps that are 'buildable_today' -- the
    single clearest 'which industries are easiest to integrate' signal."""
    by_cat = defaultdict(lambda: {"total": 0, "buildable_today": 0})
    for r in records:
        cat = r.get("category", "unknown")
        by_cat[cat]["total"] += 1
        if r.get("buildability_tier") == "buildable_today":
            by_cat[cat]["buildable_today"] += 1
    rows = []
    for cat, counts in by_cat.items():
        pct = round(100 * counts["buildable_today"] / counts["total"]) if counts["total"] else 0
        rows.append({"category": cat, "buildable_today": counts["buildable_today"], "total": counts["total"], "pct_easy": pct})
    rows.sort(key=lambda r: r["pct_easy"], reverse=True)
    return rows


def run_full_analysis(records: list[dict]) -> dict:
    total = len(records)
    mcp_official = sum(1 for r in records if "official" in (r.get("mcpSupport") or "").lower())
    mcp_third_party = sum(1 for r in records if "third-party" in (r.get("mcpSupport") or "").lower() and "official" not in (r.get("mcpSupport") or "").lower())
    mcp_none = total - mcp_official - mcp_third_party

    buildability = distribution(records, "buildability_tier")
    gate_types = distribution(records, "gate_type")
    auth_dist = distribution(records, "auth_primary")
    category_dist = distribution(records, "category")
    api_type_dist = distribution(records, "api_type_primary")

    self_serve_count = sum(1 for r in records if "self-serve" in (r.get("selfServe") or "").lower() and "gated" not in (r.get("selfServe") or "").lower())
    gated_count = sum(1 for r in records if "gated" in (r.get("selfServe") or "").lower())
    unclear_count = total - self_serve_count - gated_count

    blocker_counter = Counter()
    for r in records:
        b = (r.get("blocker") or "").strip().lower()
        if b and b != "none":
            # bucket into short reusable labels rather than 100 unique free-text strings
            if "review" in b or "approval" in b:
                blocker_counter["Platform review / app approval required"] += 1
            elif "contract" in b or "sales" in b or "application" in b:
                blocker_counter["Sales-led / contract-gated access"] += 1
            elif "plan" in b or "paywall" in b or "tier" in b or "add-on" in b:
                blocker_counter["Paid-plan / tier paywall on the API itself"] += 1
            elif "account" in b or "underwrit" in b or "kyc" in b or "merchant" in b:
                blocker_counter["Requires a real, verified business/merchant account"] += 1
            elif "no public" in b or "no discoverable" in b or "no traditional" in b or "not a toolkit" in b:
                blocker_counter["No public API surface (webhooks/CLI/closed platform only)"] += 1
            else:
                blocker_counter["Other / narrower API surface"] += 1

    confidence_buckets = Counter()
    for r in records:
        c = r.get("confidence", 0)
        if c >= 90:
            confidence_buckets["90-100 (verified this session)"] += 1
        elif c >= 75:
            confidence_buckets["75-89 (high-confidence knowledge)"] += 1
        elif c >= 60:
            confidence_buckets["60-74 (medium, flagged for re-check)"] += 1
        else:
            confidence_buckets["<60 (manual review queue)"] += 1

    avg_confidence = round(sum(r.get("confidence", 0) for r in records) / total, 1) if total else 0

    return {
        "total_apps": total,
        "avg_confidence": avg_confidence,
        "mcp_official": mcp_official,
        "mcp_third_party": mcp_third_party,
        "mcp_none": mcp_none,
        "buildability_distribution": buildability,
        "gate_type_distribution": gate_types,
        "auth_distribution": auth_dist,
        "category_distribution": category_dist,
        "api_type_distribution": api_type_dist,
        "self_serve_vs_gated": {"self_serve": self_serve_count, "gated": gated_count, "unclear": unclear_count},
        "blocker_distribution": dict(blocker_counter.most_common()),
        "confidence_distribution": dict(confidence_buckets),
        "category_ease_ranking": category_ease_ranking(records),
        "manual_review_queue_size": sum(1 for r in records if r.get("confidence", 0) < 65),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data.apps_dataset import APPS  # noqa: E402
    from agents.classifier import enrich_all  # noqa: E402

    enriched = enrich_all(APPS)
    result = run_full_analysis(enriched)
    print(json.dumps(result, indent=2))
