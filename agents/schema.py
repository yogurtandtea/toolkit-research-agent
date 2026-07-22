"""
schema.py -- shared data model for the research pipeline.

Every agent in this pipeline reads and writes AppRecord objects in this shape.
Keeping one dataclass as the single source of truth means the Extraction,
Verification, and Report agents can't silently drift out of sync on field names.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class AppRecord:
    name: str
    category: str
    description: str = ""
    authentication: list[str] = field(default_factory=list)
    selfServe: str = ""
    apiTypes: list[str] = field(default_factory=list)
    webhooks: Optional[bool] = None
    graphql: bool = False
    soap: bool = False
    mcpSupport: str = ""
    toolkitVerdict: str = ""
    blocker: str = ""
    confidence: int = 0
    evidence: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AppRecord":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def load_dataset(path: str) -> list[AppRecord]:
    with open(path) as f:
        raw = json.load(f)
    return [AppRecord.from_dict(r) for r in raw]


def save_dataset(records: list[AppRecord], path: str) -> None:
    with open(path, "w") as f:
        json.dump([r.to_dict() for r in records], f, indent=2)
