"""M15 — Benchmark harness (SPEC §15). Runs the decision core twice over identical scenarios:
once with each pairwise BASELINE policy, once with OCI, and reports every metric including
the ones where OCI loses. Built at step 3, run continuously. Evidence over marketing (§15.6).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from oci.bench.baselines import BASELINES
from oci.config import CONFIG
from oci.data.synthetic import Scenario, load
from oci.decide.optimize import Strategy, evaluate, generate_strategies, references_for, cost_vector
from oci.decide.validate import validate
from oci.graph.build import build_graph
from oci.ledger.compute import sk_budget_mps_per_day
from oci.physics.screen import screen
from oci.sim.simulate import OrbitalState, simulate

SCENARIO_SET = {
    "S1": ("two_body_head_on", "sanity — OCI should roughly tie B1/B2, not win"),
    "S2": ("keystone_cluster", "five/six-object cluster, keystone ≠ max-Pc: the core graph claim"),
    "S3": ("voi_event", "high uncertainty, long lead: WAIT should dominate"),
    "S5": ("dead_rocket_body", "dead-object-dominated cluster: attribution; avoidance cannot fix it"),
}


@dataclass
class Metrics:
    policy: str
    action: str
    collision_risk_final: float
    future_conjunctions_72h: int
    total_dv_mps: float
    n_maneuvers: int
    n_operators_burdened: int
    mission_impact: float
    systemic_cost: float
    expected_cost: Optional[float]
    p95_cost: Optional[float]
    max_regret: Optional[float]
    validator: str
    runtime_s: float


@dataclass
class BenchResult:
    scenario_id: str
    scenario_name: str
    seed: int
    pc_threshold: float
    covariance_source: str
    rows: list[Metrics]
    verdict: str
    verdict_detail: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({**{k: v for k, v in asdict(self).items() if k != "rows"}, "rows": [asdict(r) for r in self.rows],
                           "assumptions": CONFIG.assumptions_block()}, indent=2, default=str)


def _metrics_for(s: Strategy, cluster, state: OrbitalState, conjs, refs, weights, runtime: float) -> Metrics:
    sim = s.sim if s.sim is not None else simulate(state, s.action, conjs)
    cv = s.cost if s.cost is not None else cost_vector(sim, state, cluster, conjs, refs)
    burns = s.action.burns()
    ops = {state.objects[b.target_id].operator for b in burns}
    days = sum(b.magnitude_mps / sk_budget_mps_per_day(state.objects[b.target_id].orbit.mean_alt_km) for b in burns)
    m = set(cluster.members)
    inside = [c for c in sim.conjunctions if c.primary_id in m or c.secondary_id in m]
    pcs = [c.pc.value for c in inside if c.pc.value is not None]
    pc_star = CONFIG.thresholds.declared_pc_threshold
    if s.action.kind == "WAIT" and s.action.then is not None and s.action.expected_dv_mps is not None:
        # WAIT-then-clear: the addressed pair ends at the cleared level by construction (§11.11);
        # report the expected outcome, not a nominal simulation of the *expected* Δv.
        tgt = s.action.then.target_id
        addressed = [c for c in inside if tgt in (c.primary_id, c.secondary_id) and c.pc.value is not None and c.pc.value >= pc_star]
        if addressed:
            top = max(addressed, key=lambda c: c.pc.value).key()
            pcs = [min(c.pc.value, pc_star / CONFIG.maneuver.pc_margin) if c.key() == top else c.pc.value for c in inside if c.pc.value is not None]
    return Metrics(
        policy=s.proposed_by.split(":")[-1] if s.proposed_by.startswith("baseline") else "OCI",
        action=s.action.describe(),
        collision_risk_final=max(pcs) if pcs else 0.0,
        future_conjunctions_72h=sum(1 for p in pcs if p >= pc_star),
        total_dv_mps=s.action.total_dv_mps, n_maneuvers=len(burns), n_operators_burdened=len(ops),
        mission_impact=days / refs["days"], systemic_cost=cv.J(weights),
        expected_cost=float(s.expected_cost.value) if s.expected_cost and s.expected_cost.value is not None else None,
        p95_cost=float(s.p95_cost.value) if s.p95_cost and s.p95_cost.value is not None else None,
        max_regret=float(s.max_regret.value) if s.max_regret and s.max_regret.value is not None else None,
        validator=s.validator_verdict or "—", runtime_s=runtime,
    )


def run_scenario(scenario_id: str, seed: int = 42, n_mc: int = 100,
                 baselines: Sequence[str] = ("B1", "B2", "B3", "B4")) -> BenchResult:
    name, _ = SCENARIO_SET[scenario_id]
    sc: Scenario = load(name, seed)
    objs = {o.norad_id: o for o in sc.objects}
    scr = screen(sc.objects, sc.window_start, sc.window_end)
    graph = build_graph(scr.conjunctions, objs)
    cluster = graph.clusters[0]
    state = OrbitalState(objs, sc.window_start, frozenset(c.conj_id for c in scr.conjunctions))
    weights = CONFIG.decision.weights
    refs = references_for(cluster, scr.conjunctions)
    rows: list[Metrics] = []
    timings: dict[str, float] = {}
    policies: list[Strategy] = []
    for bid in baselines:
        t = time.perf_counter()
        s = BASELINES[bid](state, scr.conjunctions, cluster.members)
        timings[bid] = time.perf_counter() - t
        policies.append(s)
    # OCI: generate, evaluate, validate in ranking order, keep the first approved
    t = time.perf_counter()
    strategies = generate_strategies(cluster, state, scr.conjunctions)
    opt = evaluate(strategies, cluster, state, scr.conjunctions, weights=weights, n_mc=n_mc, seed=seed)
    chosen = None
    for s in opt.by_expected:
        v = validate(s.action, state, scr.conjunctions, sim=s.sim) if s.kind not in ("HOLD", "OBSERVE") else None
        s.validator_verdict = v.status if v else "APPROVED"
        if s.validator_verdict == "APPROVED":
            chosen = s
            break
    timings["OCI"] = time.perf_counter() - t
    oci_pick = Strategy("OCI", chosen.action, "oci")
    policies.append(oci_pick)
    # Evaluate ALL policies jointly on the same Monte Carlo scenarios so regret is comparable.
    evaluate(policies, cluster, state, scr.conjunctions, weights=weights, n_mc=n_mc, seed=seed)
    for s in policies:
        s.validator_verdict = validate(s.action, state, scr.conjunctions, sim=s.sim).status if s.kind not in ("HOLD", "OBSERVE") else "APPROVED"
        rows.append(_metrics_for(s, cluster, state, scr.conjunctions, refs, weights, timings[s.strategy_id if s.strategy_id != "OCI" else "OCI"]))
    # verdict vs B2 (the honest baseline)
    b2 = next(r for r in rows if r.policy == "B2")
    oci = rows[-1]
    detail = {}
    better = worse = 0
    for k, lower_is_better in (("systemic_cost", True), ("total_dv_mps", True), ("future_conjunctions_72h", True),
                               ("max_regret", True), ("collision_risk_final", True), ("mission_impact", True), ("p95_cost", True)):
        a, b = getattr(oci, k), getattr(b2, k)
        if a is None or b is None:
            continue
        if abs(a - b) <= 1e-9 * max(1.0, abs(b)):
            detail[k] = "tie"
        elif (a < b) == lower_is_better:
            detail[k] = "better"; better += 1
        else:
            detail[k] = "worse"; worse += 1
    # The objective OCI optimises is EXPECTED systemic cost (§10.7, §11.12) over the joint Monte
    # Carlo scenarios; ties within 5 % are NEUTRAL. The other rows show what was traded for it.
    a, b = oci.expected_cost, b2.expected_cost
    if a is None or b is None or abs(a - b) <= 0.05 * max(abs(b), 1e-9):
        verdict = "NEUTRAL"
    else:
        verdict = "OCI_BETTER" if a < b else "OCI_WORSE"
    detail["expected_cost"] = "tie" if verdict == "NEUTRAL" else ("better" if verdict == "OCI_BETTER" else "worse")
    return BenchResult(scenario_id, name, seed, CONFIG.thresholds.declared_pc_threshold,
                       ", ".join(sorted({o.covariance_source for o in objs.values()})), rows, verdict, detail)


def render(r: BenchResult) -> str:
    cols = [m.policy for m in r.rows]
    lines = [f"BENCHMARK  scenario {r.scenario_id} ({r.scenario_name})  seed {r.seed}  Pc threshold {r.pc_threshold:g}  cov {r.covariance_source}", ""]
    lines.append(f"{'':28s}" + "".join(f"{c:>12s}" for c in cols) + f"{'Δ vs B2':>12s}")
    b2 = next(m for m in r.rows if m.policy == "B2"); oci = r.rows[-1]
    def fmt(v, kind):
        if v is None: return "—"
        return f"{v:.1e}" if kind == "e" else (f"{v:.2f}" if kind == "f" else str(int(v)))
    def delta(k, kind):
        a, b = getattr(oci, k), getattr(b2, k)
        if a is None or b is None: return "—"
        if kind == "i": return f"{int(a - b):+d}"
        if b == 0: return "—" if a == 0 else "worse"
        return f"{(a - b) / b * 100:+.0f}%"
    spec = [("collision risk final", "collision_risk_final", "e"), ("future conjunctions 72h", "future_conjunctions_72h", "i"),
            ("total Δv (all objects) m/s", "total_dv_mps", "f"), ("manoeuvres commanded", "n_maneuvers", "i"),
            ("operators burdened", "n_operators_burdened", "i"), ("mission impact", "mission_impact", "f"),
            ("systemic cost", "systemic_cost", "f"), ("expected cost E[J]", "expected_cost", "f"),
            ("p95 cost", "p95_cost", "f"), ("max regret", "max_regret", "f"), ("runtime s", "runtime_s", "f")]
    for label, k, kind in spec:
        lines.append(f"{label:28s}" + "".join(f"{fmt(getattr(m, k), kind):>12s}" for m in r.rows) + f"{delta(k, kind):>12s}")
    lines.append("")
    for m in r.rows:
        lines.append(f"  {m.policy:4s} {m.action}  [{m.validator}]")
    lines.append("")
    wins = [k for k, v in r.verdict_detail.items() if v == "better"]
    losses = [k for k, v in r.verdict_detail.items() if v == "worse"]
    others = [w for w in wins if w != "expected_cost"]
    lines.append(f"VERDICT: {r.verdict} on expected systemic cost vs B2." + (f" Better on {', '.join(others)}." if others else ""))
    if losses:
        lines.append(f"         OCI is WORSE than B2 on {', '.join(losses)} — reported, not hidden.")
    return "\n".join(lines) + "\n"


def run_all(seed: int = 42, n_mc: int = 100, out_dir: Path | None = None) -> list[BenchResult]:
    results = []
    for sid in SCENARIO_SET:
        r = run_scenario(sid, seed=seed, n_mc=n_mc)
        results.append(r)
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"bench_{sid}_seed{seed}.json").write_text(r.to_json())
    return results
