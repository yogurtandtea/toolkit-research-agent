"""
classifier.py -- Confidence Scorer / Classification Agent

Single responsibility: post-process verified AppRecords into the clean,
consistent categorical buckets the analysis and report layers depend on --
this is where messy free-text extraction output ("gated (needs a partnership,
kind of, unless you pay for Enterprise)") gets normalized into stable enum
values used everywhere downstream.

Buckets produced:
  - buildability_tier: "buildable_today" | "buildable_gated" | "not_verifiable"
  - gate_type: "none" | "plan_paywall" | "approval_review" | "partnership_sales" | "account_verification"
  - auth_primary: the single dominant auth method, for clean chart bucketing
"""
from __future__ import annotations

import re


def classify_buildability(record: dict) -> str:
    verdict = (record.get("toolkitVerdict") or "").lower()
    if "not verifiable" in verdict or record.get("confidence", 0) < 40:
        return "not_verifiable"
    if "buildable today" in verdict:
        return "buildable_today"
    if "gated" in verdict or "partner" in verdict or "account-gated" in verdict or "plan-gated" in verdict:
        return "buildable_gated"
    if "not a toolkit" in verdict or "not buildable" in verdict:
        return "not_buildable"
    return "buildable_gated"  # conservative default: anything ambiguous is treated as needing a closer look


def classify_gate_type(record: dict) -> str:
    blocker = (record.get("blocker") or "").lower()
    self_serve = (record.get("selfServe") or "").lower()
    if blocker in ("none", "") and "self-serve" in self_serve:
        return "none"
    if any(w in blocker for w in [
        "contract", "sales", "application-only", "custom quote", "underwriting",
        "no self-serve signup", "direct data team",
    ]):
        return "partnership_sales"
    if any(w in blocker for w in [
        "review", "approval", "verification required", "business verification",
        "app review", "developer token starts", "partner application",
    ]):
        return "approval_review"
    if any(w in blocker for w in [
        "plan", "paywall", "subscription tier", "paid add-on", "enterprise-tier",
        "enterprise plan", "higher-tier", "business/enterprise plan", "enterprise beta",
    ]):
        return "plan_paywall"
    if any(w in blocker for w in [
        "account", "underwritten", "kyc", "merchant account", "seller account",
        "admin role", "admin-role", "admin provisioning", "system-admin",
    ]):
        return "account_verification"
    if any(w in blocker for w in [
        "no public api", "no discoverable", "no traditional", "not a toolkit",
        "no documented general-purpose", "not sanctioned",
    ]):
        return "no_public_api"
    if blocker in ("none", ""):
        return "none"
    return "narrow_surface_or_unverified"


API_TYPE_KEYWORDS = {
    "SOAP": ["soap"],
    "gRPC": ["grpc"],
    "Webhooks only": ["webhooks (in/out)", "webhooks only"],
    "MCP only": ["mcp (official)"],
    "Protocol / driver (Bolt, MTProto, etc.)": ["bolt", "mtproto", "gateway (websocket)", "websocket"],
    "CLI only (no hosted API)": ["cli only"],
}


def classify_api_type_primary(record: dict) -> str:
    """Collapse the free-text apiTypes list into one clean primary label per app,
    so charts show ~7 meaningful buckets instead of ~30 near-duplicate strings."""
    types = record.get("apiTypes", [])
    joined = " | ".join(types).lower()
    if not types or joined.strip() == "":
        return "Unknown"
    for label, keywords in API_TYPE_KEYWORDS.items():
        if any(k in joined for k in keywords):
            return label
    has_rest = "rest" in joined
    has_graphql = "graphql" in joined
    if has_rest and has_graphql:
        return "REST + GraphQL"
    if has_rest:
        return "REST"
    if has_graphql:
        return "GraphQL"
    return "Other"


def classify_auth_primary(record: dict) -> str:
    auths = record.get("authentication", [])
    if not auths:
        return "unknown"
    priority = ["OAuth2", "API key", "Bearer token", "Basic", "Token"]
    joined = " ".join(auths).lower()
    if "oauth" in joined:
        return "OAuth2"
    if "api key" in joined or "bearer" in joined or "token" in joined:
        return "API key / Token"
    if "basic" in joined:
        return "Basic"
    return "Other"


def enrich_record(record: dict) -> dict:
    record = dict(record)
    record["buildability_tier"] = classify_buildability(record)
    record["gate_type"] = classify_gate_type(record)
    record["auth_primary"] = classify_auth_primary(record)
    record["api_type_primary"] = classify_api_type_primary(record)
    return record


def enrich_all(records: list[dict]) -> list[dict]:
    return [enrich_record(r) for r in records]
