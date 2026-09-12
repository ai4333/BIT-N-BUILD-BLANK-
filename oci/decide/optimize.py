"""M7 — Strategy generation, systemic cost, and three rankings (SPEC §10.7, §11.12).

Action space: HOLD · MANEUVER(obj, Δv, t_burn) · WAIT(Δt[, then MANEUVER]) · OBSERVE(obj) ·
COORDINATE(a, b). Capped at ~40 strategies, coarse grid then refine around the best.
Cost J = w_s·Safety + w_f·FutureRisk + w_v·Fuel + w_m·Mission + w_n·Network, every term
normalised to [0, 1] against documented references. Rankings: expected, robust (p95),
minimax regret — they can disagree, and that is the point.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence

import numpy as np

from oci.config import CONFIG
from oci.graph.build import Cluster
from oci.labels import Traced, na, traced
from oci.ledger.compute import sk_budget_mps_per_day
from oci.physics.maneuver import Burn
from oci.physics.screen import Conjunction
from oci.sim.simulate import Action, OrbitalState, SimResult, simulate

_FN = "decide.optimize@0.1.0"


@dataclass
class CostVector:
    safety: float
    future: float
    fuel: float
    mission: float
    network: float
    references: dict = field(default_factory=dict)

    def J(self, w: dict[str, float]) -> float:
        return (w["safety"] * self.safety + w["future"] * self.future + w["fuel"] * self.fuel
                + w["mission"] * self.mission + w["network"] * self.network)


@dataclass
class Strategy:
    strategy_id: str
    action: Action
    proposed_by: str
    sim: Optional[SimResult] = None
    cost: Optional[CostVector] = None
    pc_after: Optional[Traced] = None
    future_conjunctions: Optional[Traced] = None
    dv_mps: Optional[Traced] = None
    mission_impact: Optional[Traced] = None
    systemic_cost: Optional[Traced] = None
    expected_cost: Optional[Traced] = None
    p95_cost: Optional[Traced] = None
    max_regret: Optional[Traced] = None
    mc_safe_fraction: Optional[Traced] = None
    mc_costs: list[float] = field(default_factory=list)
    validator_verdict: Optional[str] = None
    validator_reason: Optional[str] = None

    @property
    def kind(self) -> str:
        return self.action.kind


@dataclass
class OptimizeResult:
    strategies: list[Strategy]
    by_expected: list[Strategy]
    by_robust: list[Strategy]
    by_regret: list[Strategy]
    weights_used: dict[str, float]
    references: dict


def cluster_conjunctions(cluster: Cluster, conjs: Sequence[Conjunction]) -> list[Conjunction]:
    m = set(cluster.members)
    return [c for c in conjs if c.primary_id in m and c.secondary_id in m]


def _critical(conjs: Sequence[Conjunction], pc_star: float) -> list[Conjunction]:
    return sorted([c for c in conjs if c.pc.value is not None and c.pc.value >= pc_star],
                  key=lambda c: -(c.pc.value or 0))


def generate_strategies(cluster: Cluster, state: OrbitalState, conjs: Sequence[Conjunction],
                        include: Sequence[str] = ("HOLD", "MANEUVER", "WAIT", "OBSERVE", "COORDINATE")) -> list[Strategy]:
    dc = CONFIG.decision
    pc_star = CONFIG.thresholds.declared_pc_threshold
    cc = cluster_conjunctions(cluster, conjs)
    crit = _critical(cc, pc_star) or sorted(cc, key=lambda c: c.miss_m)[:1]
    out: list[Strategy] = []
    k = 0

    def add(action: Action, by: str = "generator"):
        nonlocal k
        k += 1
        out.append(Strategy(strategy_id=f"str_{k:02d}_{action.kind.lower()}", action=action, proposed_by=by))

    if "HOLD" in include:
        add(Action("HOLD"))
    maneuverable = [n for n in cluster.members if state.objects[n].is_maneuverable]
    if "MANEUVER" in include:
        for nid in maneuverable:
            obj = state.objects[nid]
            tcas = [c.tca for c in crit if nid in (c.primary_id, c.secondary_id)]
            if not tcas:
                continue
            tca = min(tcas)
            for lead in dc.burn_lead_orbits:
                t_burn = tca - timedelta(minutes=obj.orbit.period_min * lead)
                if t_burn <= state.epoch + timedelta(minutes=CONFIG.validator.uplink_lead_min):
                    continue
                for dv in dc.dv_grid_mps:
                    for sign in (+1.0, -1.0):
                        add(Action("MANEUVER", target_id=nid, burn=Burn(nid, (0.0, sign * dv, 0.0), t_burn)))
    if "WAIT" in include and crit:
        for w in dc.wait_options_min:
            add(Action("WAIT", wait_min=w))
            # WAIT then a small along-track burn on the keystone (if it is maneuverable)
            key = cluster.keystone_id if cluster.keystone_id in maneuverable else (maneuverable[0] if maneuverable else None)
            if key is not None:
                obj = state.objects[key]
                tcas = [c.tca for c in crit if key in (c.primary_id, c.secondary_id)]
                if tcas:
                    t_burn = min(tcas) - timedelta(minutes=obj.orbit.period_min)
                    if t_burn > state.epoch + timedelta(minutes=w + CONFIG.validator.uplink_lead_min):
                        add(Action("WAIT", wait_min=w, then=Action("MANEUVER", target_id=key, burn=Burn(key, (0.0, dc.dv_grid_mps[1], 0.0), t_burn))))
    if "OBSERVE" in include:
        for c in crit[:2]:
            for nid in (c.primary_id, c.secondary_id):
                add(Action("OBSERVE", target_id=nid))
    if "COORDINATE" in include:
        # keystone ≠ max-Pc object: a compound plan that moves both (the graph's whole point)
        if cluster.disagreement and cluster.keystone_id in maneuverable and cluster.max_pc_object_id in maneuverable:
            ka, kb = state.objects[cluster.keystone_id], state.objects[cluster.max_pc_object_id]
            for dv in dc.dv_grid_mps[:2]:
                ta = [c.tca for c in crit if ka.norad_id in (c.primary_id, c.secondary_id)]
                tb = [c.tca for c in crit if kb.norad_id in (c.primary_id, c.secondary_id)]
                if ta and tb:
                    add(Action("COORDINATE", target_id=ka.norad_id,
                               burn=Burn(ka.norad_id, (0.0, -dv, 0.0), min(ta) - timedelta(minutes=ka.orbit.period_min)),
                               partner_burn=Burn(kb.norad_id, (0.0, -dv, 0.0), min(tb) - timedelta(minutes=kb.orbit.period_min))), by="generator:keystone+maxpc")
        for c in crit[:2]:
            a, b = state.objects[c.primary_id], state.objects[c.secondary_id]
            if a.is_maneuverable and b.is_maneuverable and a.operator != b.operator:
                for dv in dc.dv_grid_mps[:3]:
                    tb_a = c.tca - timedelta(minutes=a.orbit.period_min)
                    tb_b = c.tca - timedelta(minutes=b.orbit.period_min)
                    add(Action("COORDINATE", target_id=a.norad_id,
                               burn=Burn(a.norad_id, (0.0, dv / 2, 0.0), tb_a),
                               partner_burn=Burn(b.norad_id, (0.0, -dv / 2, 0.0), tb_b)))
    # Cap by trimming MANEUVER candidates (largest |Δv| first); never drop HOLD/WAIT/OBSERVE/COORDINATE.
    if len(out) > dc.max_strategies:
        others = [s for s in out if s.kind != "MANEUVER"]
        mans = sorted([s for s in out if s.kind == "MANEUVER"], key=lambda s: s.action.total_dv_mps)
        out = others + mans[: max(dc.max_strategies - len(others), 0)]
    return out


def cost_vector(sim: SimResult, state: OrbitalState, cluster: Cluster, baseline: Sequence[Conjunction],
                refs: dict) -> CostVector:
    """§11.12.1 — normalised to [0,1] against scenario references."""
    pc_star = CONFIG.thresholds.declared_pc_threshold
    m = set(cluster.members)
    inside = [c for c in sim.conjunctions if c.primary_id in m or c.secondary_id in m]
    pcs = [c.pc.value for c in inside if c.pc.value is not None]
    safety = log_norm(max(pcs) if pcs else 0.0, pc_star)
    new_ids = set(sim.new_conj_ids)
    future_pc = sum(c.pc.value or 0.0 for c in sim.conjunctions if c.conj_id in new_ids)
    future = log_norm(future_pc, pc_star)
    fuel = min(1.0, float(sim.dv_mps.value) / refs["dv_mps"])
    days = 0.0
    for b in ([sim.action.burn, sim.action.partner_burn] + ([sim.action.then.burn] if sim.action.then and sim.action.then.burn else [])):
        if b:
            days += b.magnitude_mps / sk_budget_mps_per_day(state.objects[b.target_id].orbit.mean_alt_km)
    if sim.action.kind == "OBSERVE" or (sim.action.then and sim.action.then.kind == "OBSERVE"):
        days += refs["observe_days"]          # tasking a sensor is not free (§10.7 action space)
    mission = min(1.0, days / refs["days"])
    w_before = sum(c.pc.value or 0.0 for c in baseline if c.primary_id in m and c.secondary_id in m)
    w_after = sum(c.pc.value or 0.0 for c in inside)
    network = min(1.0, max(0.0, (w_after - w_before) / refs["network"] + 0.5))   # 0.5 = unchanged
    return CostVector(safety, future, fuel, mission, network, dict(refs))


def log_norm(pc: float, pc_star: float, decades: float = 2.0) -> float:
    """Safety / future-risk normalisation on a log scale: 0 at Pc*/10^decades, 0.5 at Pc*,
    1 at Pc*·10^decades. A linear scale saturates at 10·Pc* and cannot rank strategies that
    all leave one conjunction above threshold (measured on keystone_cluster)."""
    if pc <= 0:
        return 0.0
    return float(min(1.0, max(0.0, (math.log10(pc) - math.log10(pc_star) + decades) / (2.0 * decades))))


def references_for(cluster: Cluster, conjs: Sequence[Conjunction]) -> dict:
    dc = CONFIG.decision
    cc = cluster_conjunctions(cluster, conjs)
    total_pc = sum(c.pc.value or 0.0 for c in cc)
    return {"safety_factor": 10.0, "future_pc": max(total_pc, dc.future_pc_reference),
            "dv_mps": dc.dv_reference_mps, "days": dc.days_reference, "observe_days": dc.observe_cost_days,
            "network": max(total_pc, dc.network_reference)}


def evaluate(strategies: list[Strategy], cluster: Cluster, state: OrbitalState, conjs: Sequence[Conjunction],
             weights: dict[str, float] | None = None, n_mc: int = 0, seed: int = 42) -> OptimizeResult:
    w = weights or CONFIG.decision.weights
    refs = references_for(cluster, conjs)
    rng = np.random.default_rng(seed)
    for s in strategies:
        s.sim = simulate(state, s.action, conjs)
        s.cost = cost_vector(s.sim, state, cluster, conjs, refs)
        J = s.cost.J(w)
        s.pc_after = s.sim.pc_max
        s.future_conjunctions = s.sim.n_conjunctions_above
        s.dv_mps = s.sim.dv_mps
        s.mission_impact = traced(s.cost.mission, "normalised", "MODELLED", _FN, days_reference=refs["days"])
        s.systemic_cost = traced(J, "normalised", "MODELLED", _FN, weights=w)
        if n_mc > 0:
            s.mc_costs, safe_flags = monte_carlo_costs(s, cluster, state, conjs, w, refs, n_mc, rng)
            arr = np.asarray(s.mc_costs)
            s.expected_cost = traced(float(arr.mean()), "normalised", "MODELLED", _FN, mc_samples=n_mc)
            s.p95_cost = traced(float(np.percentile(arr, 95)), "normalised", "MODELLED", _FN, mc_samples=n_mc)
            s.mc_safe_fraction = traced(float(np.mean(safe_flags)), "fraction", "MODELLED", _FN, mc_samples=n_mc,
                                        meaning="fraction of sampled uncertainty scenarios in which max Pc over the cluster stays below Pc*")
        else:
            s.expected_cost = traced(J, "normalised", "MODELLED", _FN, mc_samples=0)
            s.p95_cost = traced(J, "normalised", "MODELLED", _FN, mc_samples=0)
            s.mc_safe_fraction = na("fraction", "MODELLED", _FN, "Monte Carlo not run (n_mc = 0)")
    # minimax regret over scenarios (§11.12.3); with n_mc = 0 the single nominal scenario is used
    n_scen = max(len(s.mc_costs) for s in strategies) if any(s.mc_costs for s in strategies) else 1
    costs = np.array([[(s.mc_costs[k] if s.mc_costs else float(s.systemic_cost.value)) for k in range(n_scen)] for s in strategies])
    best_per_scen = costs.min(axis=0)
    regret = (costs - best_per_scen).max(axis=1)
    for s, r in zip(strategies, regret):
        s.max_regret = traced(float(r), "normalised", "MODELLED", _FN, scenarios=n_scen)
    return OptimizeResult(
        strategies=strategies,
        by_expected=sorted(strategies, key=lambda s: (round(float(s.expected_cost.value), 6), s.kind != "HOLD", s.action.total_dv_mps)),
        by_robust=sorted(strategies, key=lambda s: (round(float(s.p95_cost.value), 6), s.kind != "HOLD", s.action.total_dv_mps)),
        by_regret=sorted(strategies, key=lambda s: (round(float(s.max_regret.value), 6), s.kind != "HOLD", s.action.total_dv_mps)),
        weights_used=dict(w), references=refs,
    )


def monte_carlo_costs(s: Strategy, cluster: Cluster, state: OrbitalState, conjs: Sequence[Conjunction],
                      w: dict[str, float], refs: dict, n: int, rng: np.random.Generator) -> tuple[list[float], list[bool]]:
    """§10.6 Monte Carlo: sample the miss vector in the encounter plane from the combined
    covariance (the cheap, exact projection of sampling initial states), recompute Pc for each
    cluster conjunction, and re-evaluate the cost. Re-propagating the whole neighbourhood per
    sample is unnecessary: the geometry is linear over the encounter."""
    from oci.physics.geometry import covariance_inertial, encounter_plane
    from oci.physics.pc import foster_2d
    from oci.physics.propagate import propagate
    pc_star = CONFIG.thresholds.declared_pc_threshold
    m = set(cluster.members)
    inside = [c for c in s.sim.conjunctions if (c.primary_id in m or c.secondary_id in m)]
    planes = []
    for c in inside:
        a, b = s.sim.objects_after.get(c.primary_id, state.objects[c.primary_id]), s.sim.objects_after.get(c.secondary_id, state.objects[c.secondary_id])
        if a.sigma_rtn_m is None or b.sigma_rtn_m is None:
            continue
        sa, sb = propagate(a, c.tca), propagate(b, c.tca)
        cov = covariance_inertial(a.sigma_rtn_m, sa.r_km, sa.v_kmps) + covariance_inertial(b.sigma_rtn_m, sb.r_km, sb.v_kmps)
        planes.append((encounter_plane(c.rel_r_km, c.rel_v_kmps, cov), a.hard_body_radius_m + b.hard_body_radius_m, c.conj_id in set(s.sim.new_conj_ids)))
    base = s.cost
    out, safe = [], []
    for _ in range(n):
        pcs, fut = [], 0.0
        for pl, hbr, is_new in planes:
            sample = rng.multivariate_normal(pl.miss_xy_m, pl.cov_xy_m2)
            p = foster_2d(sample, pl.cov_xy_m2, hbr)
            pcs.append(p)
            if is_new:
                fut += p
        mx = max(pcs) if pcs else 0.0
        cv = CostVector(log_norm(mx, pc_star), log_norm(fut, pc_star), base.fuel, base.mission, base.network)
        out.append(cv.J(w))
        safe.append(mx < pc_star)
    return out, safe
