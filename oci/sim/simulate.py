"""M6 — Future simulator (SPEC §10.6). A PURE FUNCTION of state: `simulate(state, action)`
never mutates its input. That purity is what makes Chaos Mode (M14) a one-liner.

Re-screening after an action is restricted to the acted-on object's neighbourhood (2-hop
graph neighbours + radial-range overlap), never the whole catalogue.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal, Optional, Sequence

import numpy as np

from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.labels import Traced, traced
from oci.physics.maneuver import Burn, apply_maneuver
from oci.physics.screen import Conjunction, radial_ranges_overlap, screen

Kind = Literal["HOLD", "MANEUVER", "WAIT", "OBSERVE", "COORDINATE"]


@dataclass(frozen=True)
class Action:
    kind: Kind
    target_id: Optional[int] = None
    burn: Optional[Burn] = None
    wait_min: float = 0.0
    partner_burn: Optional[Burn] = None       # COORDINATE
    then: Optional["Action"] = None           # WAIT → then MANEUVER; chained burns
    expected_dv_mps: Optional[float] = None   # WAIT-then-clear: E[Δv] from the VoI engine
    delay_risk: float = 0.0                   # WAIT-then-clear: P(window closes) + P(risk grows)

    def describe(self) -> str:
        if self.kind == "HOLD":
            return "HOLD"
        if self.kind == "MANEUVER" and self.burn:
            r, t, n = self.burn.dv_rtn_mps
            return f"MANEUVER {self.target_id} Δv=({r:+.3f},{t:+.3f},{n:+.3f}) m/s RTN at {self.burn.t_burn:%Y-%m-%dT%H:%M}Z"
        if self.kind == "WAIT":
            if self.then and self.expected_dv_mps is not None:
                return f"WAIT {self.wait_min:.0f} min, then clear {self.then.target_id} (E[Δv] {self.expected_dv_mps:.3f} m/s)"
            return f"WAIT {self.wait_min:.0f} min" + (f", then {self.then.describe()}" if self.then else "")
        if self.kind == "OBSERVE":
            return f"OBSERVE {self.target_id}"
        if self.kind == "COORDINATE" and self.burn and self.partner_burn:
            return (f"COORDINATE {self.burn.target_id} |Δv|={self.burn.magnitude_mps:.3f} + "
                    f"{self.partner_burn.target_id} |Δv|={self.partner_burn.magnitude_mps:.3f} m/s")
        return self.kind

    def burns(self) -> list["Burn"]:
        out = [b for b in (self.burn, self.partner_burn) if b]
        if self.then:
            out += self.then.burns()
        return out

    @property
    def total_dv_mps(self) -> float:
        dv = 0.0
        if self.burn:
            dv += self.burn.magnitude_mps
        if self.partner_burn:
            dv += self.partner_burn.magnitude_mps
        if self.then:
            dv += self.then.total_dv_mps
        return dv


@dataclass(frozen=True)
class OrbitalState:
    """Immutable snapshot: objects, the decision epoch, the known conjunction ids."""
    objects: dict[int, SpaceObject]
    epoch: datetime
    known_conj_ids: frozenset[str] = frozenset()
    horizon_h: float = CONFIG.decision.horizon_h
    covariance_scale: dict[int, float] = field(default_factory=dict)   # per-object σ multipliers

    def with_objects(self, new: dict[int, SpaceObject]) -> "OrbitalState":
        merged = dict(self.objects); merged.update(new)
        return replace(self, objects=merged)

    def scaled(self, norad_id: int, factor: float) -> "OrbitalState":
        cs = dict(self.covariance_scale); cs[norad_id] = cs.get(norad_id, 1.0) * factor
        obj = self.objects[norad_id]
        if obj.sigma_rtn_m is not None:
            new = obj.with_sigma(tuple(s * factor for s in obj.sigma_rtn_m), obj.covariance_source)
            return replace(self.with_objects({norad_id: new}), covariance_scale=cs)
        return replace(self, covariance_scale=cs)


@dataclass
class SimResult:
    action: Action
    conjunctions: list[Conjunction]
    pc_max: Traced
    n_conjunctions_above: Traced
    sum_pc: Traced
    new_conj_ids: list[str]
    removed_conj_ids: list[str]
    dv_mps: Traced
    objects_after: dict[int, SpaceObject]
    epoch_after: datetime
    rescreened_ids: list[int]


def shrink_sigma(sigma: tuple[float, float, float], tau_before_h: float, tau_after_h: float) -> tuple[float, float, float]:
    """§10.8 Part B shrinkage σ(τ) = σ∞ + (σ0−σ∞)·exp(−λ(τ0−τ)). Until the Kelvins fit is wired
    in (block 4) the parameters come from config and are labelled `declared`."""
    lam = CONFIG.voi.lambda_per_h
    floor = CONFIG.voi.sigma_floor_fraction
    out = []
    for s in sigma:
        s_inf = s * floor
        out.append(s_inf + (s - s_inf) * math.exp(-lam * max(tau_before_h - tau_after_h, 0.0)))
    return tuple(out)  # type: ignore[return-value]


def neighbourhood(state: OrbitalState, target_ids: Sequence[int], conjs: Sequence[Conjunction]) -> list[int]:
    """2-hop graph neighbours + radial-range overlap with the target(s)."""
    ids = set(target_ids)
    adj: dict[int, set[int]] = {}
    for c in conjs:
        adj.setdefault(c.primary_id, set()).add(c.secondary_id)
        adj.setdefault(c.secondary_id, set()).add(c.primary_id)
    hop1 = set().union(*(adj.get(t, set()) for t in ids))
    hop2 = set().union(*(adj.get(t, set()) for t in hop1)) if hop1 else set()
    ids |= hop1 | hop2
    for t in list(target_ids):
        tgt = state.objects[t]
        for nid, o in state.objects.items():
            if nid != t and radial_ranges_overlap(tgt, o, CONFIG.screening.screening_volume_m):
                ids.add(nid)
    return sorted(ids)


def simulate(state: OrbitalState, action: Action, baseline_conjs: Sequence[Conjunction],
             horizon_h: float | None = None) -> SimResult:
    """Apply `action` to a copy of `state`, re-screen the affected neighbourhood over the horizon,
    and report the post-action risk. Pure: `state` is unchanged."""
    horizon_h = horizon_h or state.horizon_h
    objs = dict(state.objects)
    epoch = state.epoch
    targets: list[int] = []
    if action.kind == "MANEUVER" and action.burn:
        objs[action.burn.target_id] = apply_maneuver(objs[action.burn.target_id], action.burn)
        targets.append(action.burn.target_id)
    elif action.kind == "COORDINATE" and action.burn and action.partner_burn:
        for b in (action.burn, action.partner_burn):
            objs[b.target_id] = apply_maneuver(objs[b.target_id], b)
            targets.append(b.target_id)
    elif action.kind == "WAIT":
        epoch = epoch + timedelta(minutes=action.wait_min)
        # uncertainty shrinks for every object with covariance, per the shrinkage model
        for nid, o in list(objs.items()):
            if o.sigma_rtn_m is not None:
                nxt = min((c.tca for c in baseline_conjs if nid in (c.primary_id, c.secondary_id)), default=None)
                if nxt is not None and nxt > epoch:
                    tau0 = (nxt - state.epoch).total_seconds() / 3600.0
                    tau1 = (nxt - epoch).total_seconds() / 3600.0
                    objs[nid] = o.with_sigma(shrink_sigma(o.sigma_rtn_m, tau0, tau1), o.covariance_source)
        if action.then:
            inner = simulate(replace(state, objects=objs, epoch=epoch), action.then, baseline_conjs, horizon_h)
            return replace(inner, action=action, dv_mps=traced(action.total_dv_mps, "m/s", "COMPUTED", "sim.simulate@0.1.0"))
        targets = sorted({c.primary_id for c in baseline_conjs} | {c.secondary_id for c in baseline_conjs})
    elif action.kind == "OBSERVE" and action.target_id is not None:
        o = objs[action.target_id]
        if o.sigma_rtn_m is not None:
            objs[action.target_id] = o.with_sigma(tuple(s * CONFIG.voi.observe_shrink for s in o.sigma_rtn_m), o.covariance_source)
        targets = [action.target_id]
    else:  # HOLD
        targets = sorted({c.primary_id for c in baseline_conjs} | {c.secondary_id for c in baseline_conjs})

    if action.kind in ("MANEUVER", "COORDINATE") and action.then:
        # chained burns (e.g. baseline B2's iterated plan): apply the rest on the new state
        inner = simulate(replace(state, objects=objs, epoch=epoch), action.then, baseline_conjs, horizon_h)
        return replace(inner, action=action, dv_mps=traced(action.total_dv_mps, "m/s", "COMPUTED", "sim.simulate@0.1.0"))
    ids = neighbourhood(replace(state, objects=objs), targets, baseline_conjs) if targets else []
    t1 = epoch + timedelta(hours=horizon_h)
    subset = [objs[i] for i in ids]
    conjs = screen(subset, epoch, t1, run_id=f"sim_{action.kind.lower()}").conjunctions if len(subset) >= 2 else []
    # untouched pairs outside the neighbourhood keep their baseline conjunctions
    id_set = set(ids)
    for c in baseline_conjs:
        if (c.primary_id not in id_set or c.secondary_id not in id_set) and c.tca >= epoch and c.tca <= t1:
            conjs.append(c)
    conjs.sort(key=lambda c: c.tca)
    pc_star = CONFIG.thresholds.declared_pc_threshold
    pcs = [c.pc.value for c in conjs if c.pc.value is not None]
    base_keys = {c.key() + (int(c.tca.timestamp() // 600),) for c in baseline_conjs}
    new_keys = {c.key() + (int(c.tca.timestamp() // 600),): c.conj_id for c in conjs}
    new_ids = [cid for k, cid in new_keys.items() if k not in base_keys]
    removed = [c.conj_id for c in baseline_conjs if c.key() + (int(c.tca.timestamp() // 600),) not in new_keys and c.tca >= epoch]
    fn = "sim.simulate@0.1.0"
    return SimResult(
        action=action, conjunctions=conjs,
        pc_max=traced(max(pcs) if pcs else 0.0, "probability", "MODELLED", fn, horizon_h=horizon_h),
        n_conjunctions_above=traced(sum(1 for p in pcs if p >= pc_star), "count", "MODELLED", fn, pc_threshold=pc_star),
        sum_pc=traced(sum(pcs), "probability", "MODELLED", fn),
        new_conj_ids=new_ids, removed_conj_ids=removed,
        dv_mps=traced(action.total_dv_mps, "m/s", "COMPUTED", fn),
        objects_after=objs, epoch_after=epoch, rescreened_ids=ids,
    )
