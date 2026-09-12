"""M15 baselines (SPEC §15.2). Each is a policy: state + conjunctions → a Strategy.

B1  pairwise max-Pc: manoeuvre the maneuverable end of the highest-Pc conjunction, once.
B2  pairwise + post-manoeuvre screening: B1, then iterate while any conjunction exceeds Pc*
    (what operators actually do — the baseline OCI must beat).
B3  always-manoeuvre: burn on every alert above threshold (upper bound on Δv).
B4  never-manoeuvre: HOLD (lower bound on Δv, upper bound on risk).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Sequence

from oci.config import CONFIG
from oci.decide.optimize import Strategy
from oci.physics.maneuver import Burn, dv_to_clear
from oci.physics.screen import Conjunction
from oci.sim.simulate import Action, OrbitalState, simulate


def _critical(conjs: Sequence[Conjunction], pc_star: float) -> list[Conjunction]:
    return sorted([c for c in conjs if c.pc.value is not None and c.pc.value >= pc_star], key=lambda c: -(c.pc.value or 0))


def _burn_for(c: Conjunction, state: OrbitalState, pc_star: float) -> Burn | None:
    a, b = state.objects[c.primary_id], state.objects[c.secondary_id]
    bearer, other = (a, b) if a.is_maneuverable else (b, a)
    if not bearer.is_maneuverable:
        return None
    r = dv_to_clear(bearer, other, c.tca, pc_star)
    if r.dv_mps.value is None or r.t_burn is None:
        return None
    if r.t_burn < state.epoch + timedelta(minutes=CONFIG.validator.uplink_lead_min):
        return None
    vec = tuple((r.dv_mps.value if d == r.direction else 0.0) for d in "RTN")
    return Burn(bearer.norad_id, vec, r.t_burn)


def b1_pairwise_max_pc(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int]) -> Strategy:
    pc_star = CONFIG.thresholds.declared_pc_threshold
    m = set(members)
    crit = [c for c in _critical(conjs, pc_star) if c.primary_id in m and c.secondary_id in m]
    if not crit:
        return Strategy("B1", Action("HOLD"), "baseline:B1")
    burn = _burn_for(crit[0], state, pc_star)
    if burn is None:
        return Strategy("B1", Action("HOLD"), "baseline:B1")
    return Strategy("B1", Action("MANEUVER", target_id=burn.target_id, burn=burn), "baseline:B1")


def b2_pairwise_with_rescreen(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int]) -> Strategy:
    """Iterate B1: after each burn, re-screen and address the next conjunction above threshold."""
    from oci.decide.iterate import max_pc_first
    action = max_pc_first(state, conjs, members)
    return Strategy("B2", action or Action("HOLD"), "baseline:B2")


def b3_always_maneuver(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int]) -> Strategy:
    pc_star = CONFIG.thresholds.declared_pc_threshold
    m = set(members)
    burns: list[Burn] = []
    seen: set[int] = set()
    for c in _critical(conjs, pc_star):
        if c.primary_id not in m or c.secondary_id not in m:
            continue
        b = _burn_for(c, state, pc_star)
        if b is not None and b.target_id not in seen:
            burns.append(b); seen.add(b.target_id)
    return Strategy("B3", _chain(burns) if burns else Action("HOLD"), "baseline:B3")


def b4_never_maneuver(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int]) -> Strategy:
    return Strategy("B4", Action("HOLD"), "baseline:B4")


def _chain(burns: list[Burn]) -> Action:
    """Several burns on (possibly) different objects as one compound action. Two burns become a
    COORDINATE-shaped pair; more are chained through `then` so the simulator applies them all."""
    if len(burns) == 1:
        return Action("MANEUVER", target_id=burns[0].target_id, burn=burns[0])
    head = Action("COORDINATE", target_id=burns[0].target_id, burn=burns[0], partner_burn=burns[1])
    rest = burns[2:]
    if not rest:
        return head
    return Action("COORDINATE", target_id=burns[0].target_id, burn=burns[0], partner_burn=burns[1], then=_chain(rest))


BASELINES = {"B1": b1_pairwise_max_pc, "B2": b2_pairwise_with_rescreen, "B3": b3_always_maneuver, "B4": b4_never_maneuver}
