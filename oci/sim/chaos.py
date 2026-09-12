"""M14 — Chaos mode (SPEC §10.13, §16.4).

    chaos(state, injection) → state'         pure: the input state is untouched
    replan(previous, injection)              re-simulates the previous recommendation on state',
                                             marks it INVALIDATED with the reason when it no longer
                                             holds, re-runs the pipeline on the affected cluster, and
                                             returns the diff {was, now, why}

Injections (spec table): NEW_OBJECT, COVARIANCE_SPIKE, THIRD_PARTY_MANEUVER, TRACKING_GAP,
REFUSE_COORDINATION, UPLINK_DELAY, CONSTELLATION_INSERT. Every injection is seeded and
reproducible; the result carries what was injected so the UI can say it out loud.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Optional, Sequence

import numpy as np

from oci.config import CONFIG, MU_EARTH_KM3_S2, R_EARTH_KM
from oci.data.objects import Elements, SpaceObject, mass_model
from oci.data.synthetic import SIGMA_HIGH, crossing_state, object_from_state
from oci.decide.validate import validate
from oci.physics.maneuver import Burn, apply_maneuver
from oci.physics.propagate import propagate
from oci.physics.screen import Conjunction
from oci.pipeline import PipelineResult, run_on_state
from oci.sim.simulate import OrbitalState, pc_star_of, simulate

KINDS = ("NEW_OBJECT", "COVARIANCE_SPIKE", "THIRD_PARTY_MANEUVER", "TRACKING_GAP",
         "REFUSE_COORDINATION", "UPLINK_DELAY", "CONSTELLATION_INSERT")


@dataclass(frozen=True)
class Injection:
    kind: str
    params: dict = field(default_factory=dict)
    seed: int = 42

    def describe(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.kind}({p})"


@dataclass
class ChaosResult:
    injection: Injection
    applied: dict                           # what was actually injected (ids, times, factors)
    previous: PipelineResult
    new: PipelineResult
    invalidated: list[str]                  # strategy ids of the previous recommendation(s)
    invalidation_reason: str
    still_valid: bool                       # previous recommendation survives the injection
    diff: dict                              # {was, now, why, pc_before, pc_after, ...}
    elapsed_s: float


# ── the injections ─────────────────────────────────────────────────────────────────────────
def _cluster_members(prev: PipelineResult) -> list[int]:
    return list(prev.cluster.members) if prev.cluster else list(prev.state.objects)


def _critical_tca(prev: PipelineResult) -> Optional[datetime]:
    pc_star = pc_star_of(prev.state)
    crit = [c for c in prev.screening.conjunctions if c.pc.value is not None and c.pc.value >= pc_star]
    return min((c.tca for c in crit), default=None)


def _recommended_burn_target(prev: PipelineResult) -> Optional[int]:
    if prev.recommendation is None:
        return None
    a = prev.recommendation.action
    b = a.burn or (a.then.burn if a.then else None)
    return b.target_id if b else a.target_id


def inject_new_object(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    """A fresh, poorly tracked debris object on a trajectory that meets `target_id` at
    `t_inject` with miss `miss_m`. Default target: the object the previous recommendation moves
    (so the injection lands on the post-burn path when there is one); default time: 90 min
    after the critical TCA, inside the horizon."""
    p = inj.params
    target = int(p.get("target_id") or _recommended_burn_target(prev) or _cluster_members(prev)[0])
    tca0 = _critical_tca(prev) or (state.epoch + timedelta(hours=6))
    t_inject = datetime.fromisoformat(p["t_inject"]) if p.get("t_inject") else tca0 + timedelta(minutes=float(p.get("offset_min", 90.0)))
    miss = float(p.get("miss_m", 160.0))
    # place it on the path the target will actually fly if the previous recommendation is executed
    tgt = state.objects[target]
    if prev.recommendation is not None and prev.recommendation.sim is not None:
        tgt = prev.recommendation.sim.objects_after.get(target, tgt)
    st = propagate(tgt, t_inject)
    rng = np.random.default_rng(inj.seed)
    r, v = crossing_state(st.r_km, st.v_kmps, float(p.get("crossing_angle_deg", rng.uniform(60.0, 150.0))), miss,
                          miss_dir_deg=float(rng.uniform(0.0, 360.0)))
    nid = int(p.get("norad_id", 99900 + inj.seed % 100))
    new = object_from_state(nid, "CHAOS-NEW-DEBRIS", r, v, t_inject, object_type="DEBRIS", operator="UNKNOWN-OPERATOR",
                            is_active=False, is_maneuverable=False, sigma=SIGMA_HIGH, rcs="SMALL")
    return state.with_objects({nid: new}), {"norad_id": nid, "against": target, "t_inject": t_inject.isoformat(), "miss_m": miss,
                                            "on_post_burn_path": prev.recommendation is not None}


def inject_covariance_spike(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    p = inj.params
    ids = [int(x) for x in p.get("norad_ids", [])] or [_recommended_burn_target(prev) or _cluster_members(prev)[0]]
    factor = float(p.get("factor", 5.0))
    s = state
    for nid in ids:
        s = s.scaled(nid, factor)
    return s, {"norad_ids": ids, "factor": factor}


def inject_third_party_maneuver(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    """An unannounced burn by an object OUTSIDE the cluster (or the given one)."""
    p = inj.params
    members = set(_cluster_members(prev))
    cands = [nid for nid, o in state.objects.items() if nid not in members and o.is_maneuverable] or \
            [nid for nid in state.objects if nid not in members] or list(state.objects)
    nid = int(p.get("norad_id", cands[0]))
    dv = float(p.get("dv_mps", 0.5))
    t_burn = datetime.fromisoformat(p["t_burn"]) if p.get("t_burn") else state.epoch + timedelta(minutes=float(p.get("offset_min", 20.0)))
    burn = Burn(nid, (0.0, dv, 0.0), t_burn)
    return state.with_objects({nid: apply_maneuver(state.objects[nid], burn)}), {"norad_id": nid, "dv_mps": dv, "t_burn": t_burn.isoformat(), "announced": False}


def inject_tracking_gap(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    """Time advances without new observations: the epoch moves, σ does NOT shrink (§10.8 Part B
    would have shrunk it), so lead-time constraints bite and WAIT loses its value."""
    hours = float(inj.params.get("hours", 3.0))
    new_epoch = state.epoch + timedelta(hours=hours)
    s = replace(state, epoch=new_epoch, policy={**state.policy, "note": f"tracking gap {hours:g} h: no covariance shrinkage"})
    return s, {"hours": hours, "new_epoch": new_epoch.isoformat(), "sigma_unchanged": True}


def inject_refuse_coordination(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    ex = set(state.policy.get("excluded_kinds", ())) | {"COORDINATE"}
    return replace(state, policy={**state.policy, "excluded_kinds": tuple(sorted(ex))}), {"excluded_kinds": sorted(ex)}


def inject_uplink_delay(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    lead = float(inj.params.get("uplink_lead_min", 180.0))
    return replace(state, policy={**state.policy, "uplink_lead_min": lead}), {"uplink_lead_min": lead, "default": CONFIG.validator.uplink_lead_min}


def inject_constellation(state: OrbitalState, prev: PipelineResult, inj: Injection) -> tuple[OrbitalState, dict]:
    """N coordinated satellites in a shell (links to M10). Circular orbits at `alt_km`,
    `inclination_deg`, planes and phases spread uniformly, seeded."""
    p = inj.params
    n = int(p.get("n", 12))          # small by default: every strategy re-screens the neighbourhood (< 10 s budget)
    alt = float(p.get("alt_km", next(iter(state.objects.values())).orbit.mean_alt_km))
    inc = float(p.get("inclination_deg", 53.0))
    rng = np.random.default_rng(inj.seed)
    a = R_EARTH_KM + alt
    mm_rev = math.sqrt(MU_EARTH_KM3_S2 / a ** 3) * 86400.0 / (2 * math.pi)
    mm = mass_model("PAYLOAD", "MEDIUM")
    new = {}
    for k in range(n):
        nid = 98000 + k
        el = Elements(epoch=state.epoch, mean_motion_rev_day=mm_rev, eccentricity=0.0003, inclination_deg=inc,
                      raan_deg=float(rng.uniform(0, 360)), argp_deg=0.0, mean_anomaly_deg=float(rng.uniform(0, 360)),
                      bstar=0.0, mean_motion_dot=0.0, mean_motion_ddot=0.0)
        new[nid] = SpaceObject(norad_id=nid, object_name=f"CHAOS-CONST-{k:03d}", object_type="PAYLOAD", is_active=True, is_maneuverable=True,
                               operator="CHAOS-CONSTELLATION", elements=el, source="synthetic", sigma_rtn_m=(40.0, 250.0, 35.0),
                               covariance_source="declared", **mm)
    return state.with_objects(new), {"n": n, "alt_km": alt, "inclination_deg": inc, "operator": "CHAOS-CONSTELLATION"}


INJECTORS = {
    "NEW_OBJECT": inject_new_object, "COVARIANCE_SPIKE": inject_covariance_spike, "THIRD_PARTY_MANEUVER": inject_third_party_maneuver,
    "TRACKING_GAP": inject_tracking_gap, "REFUSE_COORDINATION": inject_refuse_coordination, "UPLINK_DELAY": inject_uplink_delay,
    "CONSTELLATION_INSERT": inject_constellation,
}


def chaos(state: OrbitalState, prev: PipelineResult, injection: Injection) -> tuple[OrbitalState, dict]:
    if injection.kind not in INJECTORS:
        raise ValueError(f"unknown injection {injection.kind}; one of {KINDS}")
    new_state, applied = INJECTORS[injection.kind](state, prev, injection)
    return replace(new_state, known_conj_ids=frozenset()), applied      # conjunctions are re-derived, never carried


# ── invalidation and replan ───────────────────────────────────────────────────────────────
def _check_previous(prev: PipelineResult, new_state: OrbitalState, new_conjs: Sequence[Conjunction]) -> tuple[bool, str, dict]:
    """Re-simulate the previous recommendation on the new state (pure) and re-validate it."""
    pc_star = pc_star_of(new_state)
    rec = prev.recommendation
    if rec is None:
        return False, "there was no previous recommendation", {}
    old_pc = rec.pc_after.value if rec.pc_after else None
    sim = simulate(new_state, rec.action, list(new_conjs))
    pc_after = sim.pc_max.value
    new_above = [c for c in sim.conjunctions if c.conj_id in set(sim.new_conj_ids) and c.pc.value is not None and c.pc.value >= pc_star]
    v = validate(rec.action, new_state, list(new_conjs), sim=sim)
    detail = {"pc_after_before_injection": old_pc, "pc_after_on_new_state": pc_after, "new_conjunctions_above_threshold": len(new_above),
              "validator": v.status, "validator_reason": v.reason}
    if v.status == "REJECTED":
        return False, f"validator now rejects it: {v.reason}", detail
    if new_above:
        c = new_above[0]
        return False, (f"the injected change creates a conjunction with the post-action trajectory: {c.primary_id} vs {c.secondary_id} "
                       f"at {c.tca:%Y-%m-%dT%H:%M}Z, miss {c.miss_distance_m.value:.0f} m, Pc {c.pc.value:.2e}"), detail
    if pc_after is not None and pc_after >= pc_star and rec.action.kind != "HOLD":
        return False, f"post-action max Pc is now {pc_after:.2e} ≥ Pc* {pc_star:g} (was {old_pc:.2e})", detail
    if rec.action.kind == "HOLD" and pc_after is not None and pc_after >= pc_star:
        return False, f"HOLD is no longer safe: max Pc {pc_after:.2e} ≥ Pc* {pc_star:g}", detail
    return True, "previous recommendation re-simulated on the new state and still holds", detail


def replan(prev: PipelineResult, injection: Injection, n_mc: int = 25, seed: Optional[int] = None) -> ChaosResult:
    t = time.perf_counter()
    seed = injection.seed if seed is None else seed
    new_state, applied = chaos(prev.state, prev, injection)
    new_state = replace(new_state, policy={**new_state.policy, "max_strategies": CONFIG.decision.max_strategies_chaos})
    focus = _recommended_burn_target(prev) or (prev.cluster.members[0] if prev.cluster else None)
    window_end = prev.window_end or (new_state.epoch + timedelta(hours=CONFIG.decision.horizon_h))
    new = run_on_state(new_state, window_end, f"{prev.scenario}+{injection.kind}", n_mc=n_mc, seed=seed,
                       validate_all=True, focus_cluster_member=focus)
    ok, reason, detail = _check_previous(prev, new.state, new.screening.conjunctions)
    was = prev.recommendation.action.describe() if prev.recommendation else "none"
    now = new.recommendation.action.describe() if new.recommendation else "none (no approved strategy)"
    if not ok:
        why = f"INVALIDATED — {reason}. Replanned on the affected cluster: {now}."
    elif was != now:
        why = f"previous recommendation still feasible, but no longer optimal under the new state: {now} has lower expected systemic cost."
    else:
        why = "unchanged: the injection does not touch this cluster's decision."
    diff = {"was": was, "now": now, "why": why, "changed": was != now, **detail,
            "n_conjunctions_before": len(prev.screening.conjunctions), "n_conjunctions_after": len(new.screening.conjunctions),
            "rejected_before": [s.strategy_id for s in prev.rejected], "rejected_after": [s.strategy_id for s in new.rejected]}
    inval = [prev.recommendation.strategy_id] if (prev.recommendation and not ok) else []
    return ChaosResult(injection, applied, prev, new, inval, reason if not ok else "", ok, diff, time.perf_counter() - t)


def render(res: ChaosResult) -> str:
    L = ["═" * 78, f" CHAOS  {res.injection.describe()} · applied {res.applied}",
         f"   conjunctions {res.diff['n_conjunctions_before']} → {res.diff['n_conjunctions_after']} · replan {res.elapsed_s:.1f} s"]
    if res.invalidated:
        L.append(f"   ✗ previous recommendation {res.invalidated[0]} INVALIDATED: {res.invalidation_reason}")
    else:
        L.append(f"   ✓ previous recommendation still valid on the new state")
    L += [f"   WAS: {res.diff['was']}", f"   NOW: {res.diff['now']}", f"   WHY: {res.diff['why']}"]
    if res.diff.get("pc_after_on_new_state") is not None:
        L.append(f"   previous plan's post-action max Pc: {res.diff['pc_after_before_injection']:.2e} → {res.diff['pc_after_on_new_state']:.2e}"
                 f" · validator on new state: {res.diff['validator']}")
    if res.new.rejected:
        L.append(f"   rejected after replan: " + "; ".join(f"{s.strategy_id} ({s.validator_reason[:60]})" for s in res.new.rejected[:4]))
    L.append("═" * 78)
    return "\n".join(L)
