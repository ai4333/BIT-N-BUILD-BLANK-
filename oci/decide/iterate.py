"""Iterated clearing plans: burn, re-screen, burn again until nothing in the cluster exceeds Pc*.

Used both by baseline B2 (max-Pc first — standard operational practice) and by OCI's generator
(keystone-first, and max-Pc first as a candidate), so that OCI's strategy set always contains
the standard-practice plan and can only improve on it.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Callable, Optional, Sequence

from oci.config import CONFIG
from oci.physics.maneuver import Burn, dv_to_clear
from oci.physics.screen import Conjunction
from oci.sim.simulate import Action, OrbitalState, simulate


def critical(conjs: Sequence[Conjunction], members: Sequence[int], pc_star: float) -> list[Conjunction]:
    m = set(members)
    return sorted([c for c in conjs if c.pc.value is not None and c.pc.value >= pc_star and c.primary_id in m and c.secondary_id in m],
                  key=lambda c: -(c.pc.value or 0))


def burn_to_clear(c: Conjunction, state: OrbitalState, pc_star: float, prefer: Optional[int] = None) -> Optional[Burn]:
    a, b = state.objects[c.primary_id], state.objects[c.secondary_id]
    if prefer is not None and prefer in (a.norad_id, b.norad_id) and state.objects[prefer].is_maneuverable:
        bearer = state.objects[prefer]; other = b if bearer is a else a
    else:
        bearer, other = (a, b) if a.is_maneuverable else (b, a)
    if not bearer.is_maneuverable:
        return None
    r = dv_to_clear(bearer, other, c.tca, pc_star)
    if r.dv_mps.value is None or r.t_burn is None or r.t_burn < state.epoch + timedelta(minutes=CONFIG.validator.uplink_lead_min):
        return None
    return Burn(bearer.norad_id, tuple((r.dv_mps.value if d == r.direction else 0.0) for d in "RTN"), r.t_burn)


def chain(burns: list[Burn]) -> Action:
    if len(burns) == 1:
        return Action("MANEUVER", target_id=burns[0].target_id, burn=burns[0])
    rest = burns[2:]
    return Action("COORDINATE", target_id=burns[0].target_id, burn=burns[0], partner_burn=burns[1], then=chain(rest) if rest else None)


def iterated_plan(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int],
                  pick: Callable[[list[Conjunction], OrbitalState], Optional[Burn]], max_iter: int = 4) -> Optional[Action]:
    """Generic loop: `pick` chooses the next burn from the current critical list; stop when clear."""
    cur_state, cur_conjs = state, list(conjs)
    burns: list[Burn] = []
    pc_star = CONFIG.thresholds.declared_pc_threshold
    for _ in range(max_iter):
        crit = critical(cur_conjs, members, pc_star)
        if not crit:
            break
        burn = pick(crit, cur_state)
        if burn is None or any(b.target_id == burn.target_id and abs((b.t_burn - burn.t_burn).total_seconds()) < 60 for b in burns):
            break
        burns.append(burn)
        sim = simulate(cur_state, Action("MANEUVER", target_id=burn.target_id, burn=burn), cur_conjs)
        cur_state = replace(cur_state, objects=sim.objects_after)
        cur_conjs = sim.conjunctions
    return chain(burns) if burns else None


def max_pc_first(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int]) -> Optional[Action]:
    pc_star = CONFIG.thresholds.declared_pc_threshold
    return iterated_plan(state, conjs, members, lambda crit, st: burn_to_clear(crit[0], st, pc_star))


def keystone_first(state: OrbitalState, conjs: Sequence[Conjunction], members: Sequence[int], keystone_id: int) -> Optional[Action]:
    """Prefer burns on the keystone object while it is party to a critical conjunction."""
    pc_star = CONFIG.thresholds.declared_pc_threshold

    def pick(crit, st):
        mine = [c for c in crit if keystone_id in (c.primary_id, c.secondary_id)]
        if mine and st.objects[keystone_id].is_maneuverable:
            return burn_to_clear(mine[0], st, pc_star, prefer=keystone_id)
        return burn_to_clear(crit[0], st, pc_star)
    return iterated_plan(state, conjs, members, pick)
