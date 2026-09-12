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
    deferred_dv_mps: float = 0.0

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

    # Physics-informed candidates: for every maneuverable object in a critical conjunction, the
    # burn that actually clears it (direction + magnitude from dv_to_clear), at 0.6×, 1× and 1.5×.
    from oci.physics.maneuver import dv_to_clear
    clearing: dict[int, Burn] = {}
    for c in crit:
        for nid in (c.primary_id, c.secondary_id):
            if nid in maneuverable and nid not in clearing:
                other = state.objects[c.secondary_id if nid == c.primary_id else c.primary_id]
                r = dv_to_clear(state.objects[nid], other, c.tca, pc_star)
                if r.dv_mps.value is not None and r.t_burn is not None and r.t_burn > state.epoch + timedelta(minutes=CONFIG.validator.uplink_lead_min):
                    clearing[nid] = Burn(nid, tuple((r.dv_mps.value if d == r.direction else 0.0) for d in "RTN"), r.t_burn)
    # Iterated plans (burn → re-screen → burn until clear): standard practice (max-Pc first) and the
    # graph's alternative (keystone first). Both are candidates, so OCI never does worse than B2 on J.
    if "MANEUVER" in include and crit:
        from oci.decide.iterate import keystone_first, max_pc_first
        a = max_pc_first(state, conjs, cluster.members)
        if a is not None:
            add(a, by="generator:iterated-maxpc")
        if cluster.keystone_id is not None and cluster.keystone_id in maneuverable:
            a2 = keystone_first(state, conjs, cluster.members, cluster.keystone_id)
            if a2 is not None and (a is None or a2.describe() != a.describe()):
                add(a2, by="generator:iterated-keystone")
    if "MANEUVER" in include:
        for nid, b in clearing.items():
            for f in (0.6, 1.0, 1.5):
                add(Action("MANEUVER", target_id=nid, burn=Burn(nid, tuple(x * f for x in b.dv_rtn_mps), b.t_burn)), by="generator:clearing")
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
        # WAIT alone, and WAIT-then-clear priced by the VoI engine (§11.11): the follow-up burn is
        # the expected clearing Δv under the refined covariance, and the delay risk is carried in
        # the action so cost_vector can charge it. A fixed follow-up burn is not a plan.
        from oci.decide.voi import compute_voi
        top = crit[0]
        voi = compute_voi(top, state.objects, state.epoch, wait_options_min=dc.wait_options_min, n_samples=120)
        for opt in voi.options:
            add(Action("WAIT", wait_min=opt.wait_min))
            if opt.feasible and cluster.keystone_id is not None:
                key = top.primary_id if state.objects[top.primary_id].is_maneuverable else top.secondary_id
                if not state.objects[key].is_maneuverable:
                    continue
                other = state.objects[top.secondary_id if key == top.primary_id else top.primary_id]
                t_burn = top.tca - timedelta(minutes=state.objects[key].orbit.period_min)
                e_dv = float(opt.expected_dv_mps.value or 0.0)
                add(Action("WAIT", wait_min=opt.wait_min, expected_dv_mps=e_dv, delay_risk=float(opt.risk_of_delay.value or 0.0),
                           then=Action("MANEUVER", target_id=key, burn=Burn(key, (0.0, e_dv, 0.0), t_burn))), by="generator:wait-then-clear")
    if "OBSERVE" in include:
        for c in crit[:2]:
            for nid in (c.primary_id, c.secondary_id):
                add(Action("OBSERVE", target_id=nid))
    if "COORDINATE" in include:
        # keystone ≠ max-Pc object: a compound plan that moves both (the graph's whole point)
        if cluster.disagreement and cluster.keystone_id in clearing and cluster.max_pc_object_id in clearing:
            ka, kb = clearing[cluster.keystone_id], clearing[cluster.max_pc_object_id]
            for fa, fb in ((1.0, 1.0), (0.6, 1.0), (1.0, 0.6), (0.6, 0.6)):
                add(Action("COORDINATE", target_id=ka.target_id,
                           burn=Burn(ka.target_id, tuple(x * fa for x in ka.dv_rtn_mps), ka.t_burn),
                           partner_burn=Burn(kb.target_id, tuple(x * fb for x in kb.dv_rtn_mps), kb.t_burn)), by="generator:keystone+maxpc")
        elif cluster.disagreement and cluster.keystone_id in maneuverable and cluster.max_pc_object_id in maneuverable:
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
    if "COORDINATE" not in include:
        # a refused coordination also removes iterated plans that need two operators to move
        def _needs_partner(a) -> bool:
            return a is not None and (a.kind == "COORDINATE" or _needs_partner(a.then))
        out = [s for s in out if not _needs_partner(s.action)]
    if len(out) > dc.max_strategies:
        keep = [s for s in out if s.kind != "MANEUVER" or s.proposed_by != "generator"]
        blind = sorted([s for s in out if s.kind == "MANEUVER" and s.proposed_by == "generator"], key=lambda s: s.action.total_dv_mps)
        out = keep + blind[: max(dc.max_strategies - len(keep), 0)]
    return out


def cost_vector(sim: SimResult, state: OrbitalState, cluster: Cluster, baseline: Sequence[Conjunction],
                refs: dict) -> CostVector:
    """§11.12.1 — normalised to [0,1] against scenario references."""
    pc_star = CONFIG.thresholds.declared_pc_threshold
    m = set(cluster.members)
    inside = [c for c in sim.conjunctions if c.primary_id in m or c.secondary_id in m]
    pcs = [c.pc.value for c in inside if c.pc.value is not None]
    safety = log_norm(max(pcs) if pcs else 0.0, pc_star)
    cleared_pair = None
    if sim.action.kind == "WAIT" and sim.action.then is not None and sim.action.expected_dv_mps is not None:
        # The addressed pair is cleared by the (expected) follow-up burn; the risk carried for it
        # is the risk of delaying. Every OTHER conjunction still counts (found on benchmark S5).
        tgt = sim.action.then.target_id
        addressed = [c for c in inside if tgt in (c.primary_id, c.secondary_id) and c.pc.value is not None and c.pc.value >= pc_star]
        cleared_pair = max(addressed, key=lambda c: c.pc.value).key() if addressed else None
        rest = [c.pc.value for c in inside if c.pc.value is not None and c.key() != cleared_pair]
        safety = max(min(1.0, sim.action.delay_risk), log_norm(max(rest) if rest else 0.0, pc_star))
    new_ids = set(sim.new_conj_ids)
    future_pc = sum(c.pc.value or 0.0 for c in sim.conjunctions if c.conj_id in new_ids)
    # Linear against 10·Pc*: a new 5e-5 approach is a small cost, a new 1e-3 one saturates.
    future = min(1.0, future_pc / (10.0 * pc_star))
    # Fuel and mission cost count the Δv SPENT plus the Δv still OWED: any conjunction left above
    # Pc* after the action will still force a burn later. Without the deferred term the optimiser
    # preferred a cheap plan that left a 2e-4 encounter in place (found by the benchmark, S2).
    days = 0.0
    for b in sim.action.burns():
        days += b.magnitude_mps / sk_budget_mps_per_day(state.objects[b.target_id].orbit.mean_alt_km)
    deferred_dv, deferred_days = deferred_clearance(sim, state, cluster, pc_star, skip_pair=cleared_pair)
    fuel = min(1.0, (float(sim.dv_mps.value) + deferred_dv) / refs["dv_mps"])
    days += deferred_days
    if sim.action.kind == "OBSERVE" or (sim.action.then and sim.action.then.kind == "OBSERVE"):
        days += refs["observe_days"]          # tasking a sensor is not free (§10.7 action space)
    mission = min(1.0, days / refs["days"])
    w_before = sum(c.pc.value or 0.0 for c in baseline if c.primary_id in m and c.secondary_id in m)
    w_after = sum(c.pc.value or 0.0 for c in inside)
    network = min(1.0, max(0.0, (w_after - w_before) / refs["network"] + 0.5))   # 0.5 = unchanged
    return CostVector(safety, future, fuel, mission, network, dict(refs), deferred_dv)


def log_norm(pc: float, pc_star: float, decades: float = 2.0) -> float:
    """Safety normalisation. Flat at 0 below Pc*/margin (the operational "cleared" level — no
    reward for burning fuel to chase Pc to 1e-13, which S1 exposed); linear 0→0.5 from
    Pc*/margin to Pc*; log 0.5→1 from Pc* to Pc*·10^decades so plans that all leave one
    conjunction above threshold can still be ranked."""
    if pc <= 0:
        return 0.0
    cleared = pc_star / CONFIG.maneuver.pc_margin
    if pc <= cleared:
        return 0.0
    if pc <= pc_star:
        return 0.5 * (pc - cleared) / (pc_star - cleared)
    return float(min(1.0, 0.5 + 0.5 * math.log10(pc / pc_star) / decades))


_DEFERRED_CACHE: dict[tuple, tuple[float, float]] = {}


def deferred_clearance(sim: SimResult, state: OrbitalState, cluster: Cluster, pc_star: float,
                       skip_pair: Optional[tuple[int, int]] = None) -> tuple[float, float]:
    """Δv (m/s) and mission-days a maneuverable bearer would still have to spend to clear every
    cluster conjunction that remains above Pc* after the action. Cached per (pair, TCA minute)."""
    from oci.physics.maneuver import dv_to_clear
    m = set(cluster.members)
    dv_sum = days_sum = 0.0
    for c in sim.conjunctions:
        if c.pc.value is None or c.pc.value < pc_star or not (c.primary_id in m or c.secondary_id in m):
            continue
        if skip_pair is not None and c.key() == skip_pair:
            continue
        a = sim.objects_after.get(c.primary_id, state.objects[c.primary_id])
        b = sim.objects_after.get(c.secondary_id, state.objects[c.secondary_id])
        bearer, other = (a, b) if a.is_maneuverable else (b, a)
        if not bearer.is_maneuverable:
            continue
        key = (c.key(), int(c.tca.timestamp() // 60), round(c.miss_m), bearer.norad_id)
        if key not in _DEFERRED_CACHE:
            r = dv_to_clear(bearer, other, c.tca, pc_star)
            dv = r.dv_mps.value if r.dv_mps.value is not None else CONFIG.maneuver.dv_max_mps
            _DEFERRED_CACHE[key] = (dv, dv / sk_budget_mps_per_day(bearer.orbit.mean_alt_km))
        dv, d = _DEFERRED_CACHE[key]
        dv_sum += dv; days_sum += d
    return dv_sum, days_sum


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
    """§10.6 Monte Carlo over the encounter-plane covariance (the exact projection of sampling
    initial states; re-propagating per sample is unnecessary — the geometry is linear over the
    encounter). Each sample is a possible *refined* miss vector, and its Pc is evaluated with
    the covariance shrunk to the tracking floor (§10.8 Part B): the result is the distribution
    of the Pc that will be reported once knowledge of the encounter sharpens. Evaluating each
    sample with the *current* covariance would double-count the uncertainty and made expected
    cost systematically optimistic for risky plans (found on benchmark S2)."""
    from oci.physics.geometry import covariance_inertial, encounter_plane
    from oci.physics.pc import foster_2d_batch
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
        floor = CONFIG.voi.sigma_floor_fraction
        cov_refined = covariance_inertial(tuple(x * floor for x in a.sigma_rtn_m), sa.r_km, sa.v_kmps) + covariance_inertial(tuple(x * floor for x in b.sigma_rtn_m), sb.r_km, sb.v_kmps)
        planes.append((encounter_plane(c.rel_r_km, c.rel_v_kmps, cov), encounter_plane(c.rel_r_km, c.rel_v_kmps, cov_refined),
                       a.hard_body_radius_m + b.hard_body_radius_m, c.conj_id in set(s.sim.new_conj_ids)))
    base = s.cost
    if not planes:
        cv = CostVector(log_norm(0.0, pc_star), 0.0, base.fuel, base.mission, base.network)
        return [cv.J(w)] * n, [True] * n
    # samples drawn in the same order as before (one per plane per iteration), evaluated in batch
    draws = np.empty((n, len(planes), 2))
    for i in range(n):
        for j, (pl, _, _, _) in enumerate(planes):
            draws[i, j] = rng.multivariate_normal(pl.miss_xy_m, pl.cov_xy_m2)
    pcs = np.empty((n, len(planes)))
    for j, (_, pl_ref, hbr, _) in enumerate(planes):
        pcs[:, j] = foster_2d_batch(draws[:, j, :], pl_ref.cov_xy_m2, hbr)
    new_mask = np.array([is_new for _, _, _, is_new in planes], dtype=bool)
    mx = pcs.max(axis=1)
    fut = pcs[:, new_mask].sum(axis=1) if new_mask.any() else np.zeros(n)
    out, safe = [], []
    for i in range(n):
        cv = CostVector(log_norm(float(mx[i]), pc_star), min(1.0, float(fut[i]) / (10.0 * pc_star)), base.fuel, base.mission, base.network)
        out.append(cv.J(w))
        safe.append(bool(mx[i] < pc_star))
    return out, safe
