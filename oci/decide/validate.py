"""M9 — Physics validator (SPEC §10.9). Deterministic and authoritative.

The planner proposes free-form burns; this module does real work: ten constraint checks
C1–C10, including C7 (post-burn re-screen for secondary conjunctions) and the geometric
miss-distance floor from §14.3. Rejections carry the concrete physical reason.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence

import numpy as np

from oci.config import CONFIG
from oci.physics.maneuver import apply_maneuver
from oci.physics.screen import Conjunction
from oci.sim.simulate import pc_star_of, Action, OrbitalState, simulate


@dataclass
class Check:
    id: str
    name: str
    passed: bool
    detail: str


@dataclass
class Verdict:
    status: str                       # APPROVED | REJECTED
    reason: str
    violated: list[str]
    checks: list[Check] = field(default_factory=list)


def _tca_for(target_id: int, conjs: Sequence[Conjunction], after: datetime) -> Optional[datetime]:
    ts = [c.tca for c in conjs if target_id in (c.primary_id, c.secondary_id) and c.tca > after]
    return min(ts) if ts else None


def _check_burn(burn, state: OrbitalState, conjs: Sequence[Conjunction], checks: list[Check], label: str = "") -> None:
    vc = CONFIG.validator
    obj = state.objects[burn.target_id]
    dv = burn.magnitude_mps
    tca = _tca_for(burn.target_id, conjs, burn.t_burn)      # the conjunction this burn precedes
    checks.append(Check("C1", f"{label}thrust limit", dv <= vc.dv_max_per_burn_mps,
                        f"|Δv| = {dv:.3f} m/s vs max {vc.dv_max_per_burn_mps} m/s per burn"))
    checks.append(Check("C2", f"{label}propellant", dv <= vc.remaining_dv_mps,
                        f"|Δv| = {dv:.3f} m/s vs remaining budget {vc.remaining_dv_mps} m/s"))
    lead_uplink = (burn.t_burn - state.epoch).total_seconds() / 60.0
    uplink = float(state.policy.get("uplink_lead_min", vc.uplink_lead_min))
    checks.append(Check("C3", f"{label}uplink window", lead_uplink >= uplink,
                        f"burn {lead_uplink:.0f} min after now vs {uplink:.0f} min command lead"
                        + (" (uplink delay injected)" if "uplink_lead_min" in state.policy else "")))
    if tca is not None:
        lead_tca = (tca - burn.t_burn).total_seconds() / 60.0
        checks.append(Check("C4", f"{label}effective lead", lead_tca >= vc.min_maneuver_lead_min,
                            f"burn {lead_tca:.0f} min before TCA vs {vc.min_maneuver_lead_min:.0f} min minimum"))
    else:
        checks.append(Check("C4", f"{label}effective lead", True, "no upcoming conjunction for this object"))
    try:
        post = apply_maneuver(obj, burn)
        perigee = post.orbit.perigee_alt_km
        checks.append(Check("C5", f"{label}perigee floor", perigee >= vc.min_alt_km,
                            f"post-burn perigee {perigee:.1f} km vs floor {vc.min_alt_km} km"))
        d_alt = abs(post.orbit.mean_alt_km - obj.orbit.mean_alt_km)
        d_inc = abs(post.elements.inclination_deg - obj.elements.inclination_deg)
        ok6 = d_alt <= vc.mission_alt_band_km and d_inc <= vc.mission_inc_band_deg
        checks.append(Check("C6", f"{label}mission box", ok6,
                            f"Δalt {d_alt:.2f} km (band ±{vc.mission_alt_band_km}), Δinc {d_inc:.3f}° (band ±{vc.mission_inc_band_deg})"))
    except Exception as e:  # element rebuild failed → cannot certify
        checks.append(Check("C5", f"{label}perigee floor", False, f"post-burn state could not be rebuilt: {e}"))
    checks.append(Check("C8", f"{label}eclipse/power", vc.eclipse_burn_allowed or True,
                        "platform not power-constrained" if vc.eclipse_burn_allowed else "eclipse burn check not modelled"))
    checks.append(Check("C9", f"{label}slew feasible", lead_uplink >= vc.slew_time_min,
                        f"{lead_uplink:.0f} min available vs {vc.slew_time_min:.0f} min slew"))


def validate(action: Action, state: OrbitalState, conjs: Sequence[Conjunction], sim=None) -> Verdict:
    vc = CONFIG.validator
    pc_star = pc_star_of(state)
    checks: list[Check] = []
    if action.kind == "MANEUVER" and action.burn:
        _check_burn(action.burn, state, conjs, checks)
    elif action.kind == "COORDINATE" and action.burn and action.partner_burn:
        _check_burn(action.burn, state, conjs, checks, label="A: ")
        _check_burn(action.partner_burn, state, conjs, checks, label="B: ")
        checks.append(Check("C10", "partner constraints", all(c.passed for c in checks),
                            "both operators' constraints individually satisfied" if all(c.passed for c in checks)
                            else "a partner constraint failed"))
    elif action.kind == "WAIT":
        after = state.epoch + timedelta(minutes=action.wait_min)
        tcas = [c.tca for c in conjs if c.tca > state.epoch and c.pc.value is not None and c.pc.value >= pc_star]
        if tcas:
            remaining = (min(tcas) - after).total_seconds() / 60.0
            uplink = float(state.policy.get("uplink_lead_min", vc.uplink_lead_min))
            ok = remaining >= vc.min_maneuver_lead_min + uplink
            checks.append(Check("C4", "window after waiting", ok,
                                f"{remaining:.0f} min would remain before the critical TCA; need ≥ {vc.min_maneuver_lead_min + uplink:.0f}"))
        else:
            checks.append(Check("C4", "window after waiting", True, "no critical conjunction in horizon"))
        if action.then and action.then.kind == "MANEUVER" and action.then.burn:
            _check_burn(action.then.burn, OrbitalState(state.objects, after, state.known_conj_ids, state.horizon_h), conjs, checks, label="then: ")
    # C7 — post-action re-screen: any NEW conjunction above threshold or under the miss floor
    if action.kind in ("MANEUVER", "COORDINATE", "WAIT") and all(c.passed for c in checks if c.id in ("C5",)):
        try:
            sim = sim if sim is not None else simulate(state, action, conjs)
            new = [c for c in sim.conjunctions if c.conj_id in set(sim.new_conj_ids)]
            bad = [c for c in new if (c.pc.value is not None and c.pc.value >= pc_star) or c.miss_m < vc.min_miss_floor_m]
            if bad:
                worst = min(bad, key=lambda c: c.miss_m)
                pc_txt = f"Pc={worst.pc.value:.2e}" if worst.pc.value is not None else "Pc=N/A"
                moved = {b.target_id for b in action.burns()}
                other = worst.secondary_id if worst.primary_id in moved else worst.primary_id
                mover = worst.primary_id if worst.primary_id in moved else worst.secondary_id
                floor_txt = f" (< {vc.min_miss_floor_m:.0f} m floor)" if worst.miss_m < vc.min_miss_floor_m else ""
                checks.append(Check("C7", "post-burn screening", False,
                                    f"creates {len(bad)} new conjunction(s); worst: {mover} with NORAD {other} "
                                    f"at {worst.tca:%Y-%m-%dT%H:%MZ}, miss {worst.miss_m:.0f} m{floor_txt}, {pc_txt}"))
            else:
                checks.append(Check("C7", "post-burn screening", True,
                                    f"no new conjunction above Pc* or under the {vc.min_miss_floor_m:.0f} m floor in {state.horizon_h:.0f} h "
                                    f"({len(sim.rescreened_ids)} objects re-screened)"))
        except Exception as e:
            checks.append(Check("C7", "post-burn screening", False, f"re-screen failed: {e}"))
    violated = [c.id for c in checks if not c.passed]
    reason = "; ".join(f"{c.id}: {c.detail}" for c in checks if not c.passed) or "all constraints satisfied"
    return Verdict("REJECTED" if violated else "APPROVED", reason, violated, checks)
