"""Attribution rules R1–R4 (SPEC §10.5 step 1, §11.7.2). Explicit, ranked, recorded per flow."""
from __future__ import annotations

from dataclasses import dataclass

from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.physics.screen import Conjunction


@dataclass(frozen=True)
class Attribution:
    imposer: SpaceObject
    bearer: SpaceObject
    share: float
    rule: str
    confidence: str
    contested: bool


def attribute(c: Conjunction, objects: dict[int, SpaceObject], rules: tuple[str, ...] | None = None) -> list[Attribution]:
    rules = rules or CONFIG.attribution.rules
    a, b = objects[c.primary_id], objects[c.secondary_id]
    out: list[Attribution] = []
    if c.intra_constellation and CONFIG.attribution.exclude_intra_constellation:
        return out                                       # R4: excluded by default
    if c.pair_class == "ACTIVE_DEAD" and "R1" in rules:
        dead, live = (a, b) if not a.is_active else (b, a)
        out.append(Attribution(dead, live, 1.0, "R1", "high", False))
    elif c.pair_class == "DEAD_DEAD" and "R2" in rules:
        out.append(Attribution(a, b, 0.5, "R2", "high", False))
        out.append(Attribution(b, a, 0.5, "R2", "high", False))
    elif c.pair_class == "ACTIVE_ACTIVE" and "R3" in rules and a.operator != b.operator:
        # split by inverse maneuverability capability; equal → 50/50
        wa = 0.0 if a.is_maneuverable else 1.0
        wb = 0.0 if b.is_maneuverable else 1.0
        if wa + wb == 0:
            sa = sb = 0.5
        else:
            sa, sb = wa / (wa + wb), wb / (wa + wb)
        if sa > 0:
            out.append(Attribution(a, b, sa, "R3", "medium", True))
        if sb > 0:
            out.append(Attribution(b, a, sb, "R3", "medium", True))
    return out
