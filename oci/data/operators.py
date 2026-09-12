"""Operator attribution from object names (SPEC §6.5). Unmatched → UNKNOWN-OPERATOR, never dropped."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_MAP = Path(__file__).with_name("operator_map.yaml")


@lru_cache(maxsize=1)
def _rules() -> list[tuple[re.Pattern, str, bool]]:
    data = yaml.safe_load(_MAP.read_text())
    return [(re.compile(r["pattern"], re.I), r["operator"], bool(r.get("coordinated", False))) for r in data["rules"]]


def coordinated_constellations() -> tuple[str, ...]:
    return tuple(sorted({op for _, op, coord in _rules() if coord}))


def match_operator(object_name: str, owner: str | None = None, object_type: str | None = None) -> str:
    for pat, op, _ in _rules():
        if pat.search(object_name or ""):
            if op in ("DEBRIS", "ROCKET-BODY"):
                # dead objects are attributed to their launching state via SATCAT owner
                return f"{op}:{owner}" if owner else op
            return op
    if object_type in ("DEBRIS", "ROCKET_BODY") and owner:
        return f"{object_type.replace('_', '-')}:{owner}"
    if owner:
        return f"UNKNOWN-OPERATOR:{owner}"
    return "UNKNOWN-OPERATOR"
