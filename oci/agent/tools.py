"""§14.2 — the planner's tool surface. Exactly these eight; adding tools makes the planner worse.

Every tool is a thin, deterministic wrapper over the physics/decision core and returns plain
JSON (Traced values serialised as dicts). The LLM never computes; it calls these.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from oci.config import CONFIG
from oci.decide.optimize import Strategy, evaluate, references_for, cost_vector
from oci.decide.validate import validate
from oci.decide.voi import compute_voi
from oci.graph.build import Cluster, GraphResult
from oci.labels import Traced
from oci.ledger.compute import LedgerResult
from oci.physics.maneuver import Burn
from oci.physics.screen import Conjunction
from oci.sim.simulate import pc_star_of, Action, OrbitalState, simulate


def _t(x: Traced) -> dict:
    return {"value": x.value, "unit": x.unit, "label": x.label, "function": x.function,
            "assumptions": x.assumptions, "na_reason": x.na_reason}


def _conj(c: Conjunction) -> dict:
    return {"conj_id": c.conj_id, "primary_id": c.primary_id, "secondary_id": c.secondary_id,
            "tca": c.tca.isoformat(), "miss_distance_m": _t(c.miss_distance_m), "rel_speed_mps": _t(c.rel_speed_mps),
            "pc": _t(c.pc), "pc_max": _t(c.pc_max), "pc_method": c.pc_method, "covariance_source": c.covariance_source,
            "dilution": c.dilution, "pair_class": c.pair_class, "intra_constellation": c.intra_constellation}


@dataclass
class ToolContext:
    """Everything the tools need: the state, the screened conjunctions, the graph, the ledger."""
    state: OrbitalState
    conjunctions: list[Conjunction]
    graph: GraphResult
    ledger: Optional[LedgerResult]
    strategies: dict[str, Strategy] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)
    capacity: Optional[object] = None          # CapacityResult, computed lazily by evaluate_deployment
    _seq: int = 0

    def cluster(self, cluster_id: str) -> Cluster:
        for c in self.graph.clusters:
            if c.cluster_id == cluster_id:
                return c
        raise KeyError(f"cluster {cluster_id} not found")

    def next_id(self, kind: str) -> str:
        self._seq += 1
        return f"agent_{self._seq:02d}_{kind.lower()}"


def get_cluster(ctx: ToolContext, cluster_id: str) -> dict:
    c = ctx.cluster(cluster_id)
    kappa = getattr(c, "kappa", None)
    members = []
    for nid in c.members:
        o = ctx.state.objects[nid]
        members.append({"norad_id": nid, "name": o.object_name, "type": o.object_type, "operator": o.operator,
                        "is_active": o.is_active, "is_maneuverable": o.is_maneuverable, "mean_alt_km": round(o.orbit.mean_alt_km, 1)})
    edges = [_conj(x) for x in ctx.conjunctions if x.primary_id in c.members and x.secondary_id in c.members]
    return {"cluster_id": c.cluster_id, "members": members, "n_edges": c.n_edges, "keystone_id": c.keystone_id,
            "keystone_selected_by": c.keystone_selected_by, "max_pc_object_id": c.max_pc_object_id,
            "max_pc_edge": list(c.max_pc_edge) if c.max_pc_edge else None, "max_pc": c.max_pc,
            "keystone_differs_from_max_pc": c.disagreement, "critical_conjunctions": c.critical_conjunctions,
            "kappa": kappa, "pc_threshold": pc_star_of(ctx.state), "conjunctions": edges}


def get_ledger_entry(ctx: ToolContext, norad_id: int) -> dict:
    if ctx.ledger is None:
        return {"error": "ledger not computed for this state"}
    for e in ctx.ledger.entries:
        if e.norad_id == norad_id:
            return {"norad_id": e.norad_id, "object_name": e.object_name, "object_type": e.object_type, "operator": e.operator,
                    "is_active": e.is_active, "is_maneuverable": e.is_maneuverable, "pc_threshold": e.pc_threshold,
                    "conjunctions_generated": _t(e.conjunctions_generated), "maneuvers_forced": _t(e.maneuvers_forced),
                    "dv_imposed_mps": _t(e.dv_imposed_mps), "mission_days_imposed": _t(e.mission_days_imposed),
                    "operators_affected": _t(e.operators_affected), "top_bearer": e.top_bearer,
                    "maneuvers_performed": _t(e.maneuvers_performed), "dv_spent_mps": _t(e.dv_spent_mps),
                    "cab": _t(e.cab), "decay_lifetime_yr_est": _t(e.decay_lifetime_yr_est),
                    "projected_lifetime_dv": _t(e.projected_lifetime_dv), "implied_fee_usd_yr": _t(e.implied_fee_usd_yr)}
    return {"error": f"no ledger entry for NORAD {norad_id}"}


def get_conjunction(ctx: ToolContext, conj_id: str) -> dict:
    for c in ctx.conjunctions:
        if c.conj_id == conj_id:
            return _conj(c)
    return {"error": f"conjunction {conj_id} not found"}


def _parse_burn(target_id: int, dv_vector_mps, t_burn) -> Burn:
    if isinstance(t_burn, str):
        t_burn = datetime.fromisoformat(t_burn.replace("Z", "+00:00"))
    return Burn(int(target_id), tuple(float(x) for x in dv_vector_mps), t_burn)


def simulate_action(ctx: ToolContext, cluster_id: str, action: str, target_id: Optional[int] = None,
                    dv_vector_mps=None, t_burn=None, wait_min: Optional[float] = None, horizon_h: float = 72.0) -> dict:
    cl = ctx.cluster(cluster_id)
    kind = action.upper()
    if kind == "MANEUVER":
        act = Action("MANEUVER", target_id=int(target_id), burn=_parse_burn(target_id, dv_vector_mps, t_burn))
    elif kind == "WAIT":
        act = Action("WAIT", wait_min=float(wait_min or 60.0))
        if target_id is not None:
            # WAIT-then-clear: the follow-up burn is the VoI engine's expected clearing Δv (§11.11)
            pc_star = pc_star_of(ctx.state)
            crit = sorted([c for c in ctx.conjunctions if c.primary_id in cl.members and c.secondary_id in cl.members
                           and int(target_id) in (c.primary_id, c.secondary_id) and c.pc.value is not None and c.pc.value >= pc_star],
                          key=lambda c: -(c.pc.value or 0))
            if crit:
                v = compute_voi(crit[0], ctx.state.objects, ctx.state.epoch, wait_options_min=[float(wait_min or 60.0)], n_samples=120, seed=CONFIG.agent.seed, pc_threshold=pc_star_of(ctx.state))
                if v.options and v.options[0].feasible:
                    o = v.options[0]
                    obj = ctx.state.objects[int(target_id)]
                    t_b = crit[0].tca - timedelta(minutes=obj.orbit.period_min)
                    e_dv = float(o.expected_dv_mps.value or 0.0)
                    act = Action("WAIT", wait_min=float(wait_min or 60.0), expected_dv_mps=e_dv, delay_risk=float(o.risk_of_delay.value or 0.0),
                                 then=Action("MANEUVER", target_id=int(target_id), burn=Burn(int(target_id), (0.0, e_dv, 0.0), t_b)))
    elif kind == "OBSERVE":
        act = Action("OBSERVE", target_id=int(target_id))
    elif kind == "COORDINATE":
        raise ValueError("COORDINATE via simulate_action needs two burns; propose them as two MANEUVER simulations, then rank")
    else:
        act = Action("HOLD")
    s = Strategy(ctx.next_id(kind), act, "agent")
    refs = references_for(cl, ctx.conjunctions)
    s.sim = simulate(ctx.state, act, ctx.conjunctions, horizon_h=horizon_h)
    s.cost = cost_vector(s.sim, ctx.state, cl, ctx.conjunctions, refs)
    ctx.strategies[s.strategy_id] = s
    new = [_conj(c) for c in s.sim.conjunctions if c.conj_id in set(s.sim.new_conj_ids)]
    return {"strategy_id": s.strategy_id, "action": act.describe(), "pc_max_after": _t(s.sim.pc_max),
            "conjunctions_above_threshold_after": _t(s.sim.n_conjunctions_above), "dv_mps": _t(s.sim.dv_mps),
            "new_conjunctions": new, "removed_conjunction_ids": s.sim.removed_conj_ids,
            "systemic_cost": round(s.cost.J(CONFIG.decision.weights), 4),
            "cost_terms": {"safety": round(s.cost.safety, 3), "future": round(s.cost.future, 3), "fuel": round(s.cost.fuel, 3),
                           "mission": round(s.cost.mission, 3), "network": round(s.cost.network, 3), "deferred_dv_mps": round(s.cost.deferred_dv_mps, 4)},
            "note": "feasibility NOT checked — call validate_action before recommending a burn"}


def run_uncertainty_analysis(ctx: ToolContext, cluster_id: str, strategy_id: str, n_samples: int = 100) -> dict:
    cl = ctx.cluster(cluster_id)
    s = ctx.strategies[strategy_id]
    evaluate([s], cl, ctx.state, ctx.conjunctions, n_mc=int(n_samples), seed=CONFIG.agent.seed)
    return {"strategy_id": s.strategy_id, "expected_cost": _t(s.expected_cost), "p95_cost": _t(s.p95_cost),
            "max_regret": _t(s.max_regret), "safe_fraction": _t(s.mc_safe_fraction),
            "meaning": "safe_fraction = fraction of sampled uncertainty scenarios (refined covariance) in which max Pc stays below Pc*; NOT a prediction accuracy"}


def compute_voi_tool(ctx: ToolContext, conj_id: str, wait_options_min=None) -> dict:
    c = next(x for x in ctx.conjunctions if x.conj_id == conj_id)
    v = compute_voi(c, ctx.state.objects, ctx.state.epoch, wait_options_min=wait_options_min, n_samples=120, seed=CONFIG.agent.seed, pc_threshold=pc_star_of(ctx.state))
    return {"conj_id": v.conj_id, "covariance_source": v.covariance_source, "cost_now": _t(v.cost_now), "dv_now_mps": _t(v.dv_now_mps),
            "options": [{"wait_min": o.wait_min, "feasible": o.feasible, "expected_sigma_reduction": _t(o.expected_sigma_reduction),
                         "expected_pc": _t(o.expected_pc), "expected_dv_mps": _t(o.expected_dv_mps),
                         "risk_of_delay": _t(o.risk_of_delay), "voi_net": _t(o.voi_net)} for o in v.options],
            "recommended_wait_min": v.recommended_wait_min}


def rank_strategies(ctx: ToolContext, cluster_id: str, strategy_ids: list[str], weights: Optional[dict] = None) -> dict:
    cl = ctx.cluster(cluster_id)
    ss = [ctx.strategies[i] for i in strategy_ids]
    r = evaluate(ss, cl, ctx.state, ctx.conjunctions, weights=weights, n_mc=CONFIG.decision.mc_samples_interactive, seed=CONFIG.agent.seed)
    def row(s: Strategy) -> dict:
        return {"strategy_id": s.strategy_id, "action": s.action.describe(), "expected_cost": s.expected_cost.value,
                "p95_cost": s.p95_cost.value, "max_regret": s.max_regret.value, "systemic_cost": s.systemic_cost.value,
                "pc_after": s.pc_after.value, "dv_mps": s.dv_mps.value,
                "safe_fraction": s.mc_safe_fraction.value if s.mc_safe_fraction else None}
    return {"weights": r.weights_used, "by_expected": [row(s) for s in r.by_expected], "by_robust": [row(s) for s in r.by_robust],
            "by_regret": [row(s) for s in r.by_regret], "expected_value_optimum": r.by_expected[0].strategy_id,
            "minimax_regret_optimum": r.by_regret[0].strategy_id, "optima_agree": r.by_expected[0] is r.by_regret[0]}


def validate_action(ctx: ToolContext, target_id: int, dv_vector_mps, t_burn) -> dict:
    burn = _parse_burn(target_id, dv_vector_mps, t_burn)
    act = Action("MANEUVER", target_id=int(target_id), burn=burn)
    v = validate(act, ctx.state, ctx.conjunctions)
    return {"verdict": v.status, "reason": v.reason, "violated": v.violated,
            "checks": [{"id": c.id, "name": c.name, "passed": c.passed, "detail": c.detail} for c in v.checks]}


def evaluate_deployment(ctx: ToolContext, n_satellites: int, target_alt_km: float, inclination_deg: float, alternatives_km=None) -> dict:
    """M10 through the registry. The capacity result is computed once per context from the
    state's catalogue (and its conjunctions, for calibration) and cached on the context."""
    from oci.capacity.deployment import DeploymentRequest, evaluate_deployment as _ed
    from oci.capacity.ocs import compute_capacity
    if ctx.capacity is None:
        objs = list(ctx.state.objects.values())
        ctx.capacity = compute_capacity(objs, ctx.conjunctions, set(ctx.state.objects), window_days=ctx.state.horizon_h / 24.0,
                                        pc_threshold=pc_star_of(ctx.state))
    req = DeploymentRequest(int(n_satellites), float(target_alt_km), float(inclination_deg),
                            alternatives_km=tuple(alternatives_km) if alternatives_km else DeploymentRequest.alternatives_km)
    d = _ed(ctx.capacity, req)
    raw = d.as_dict()

    def conv(x):
        if isinstance(x, Traced):
            return _t(x)
        if isinstance(x, dict):
            return {k: conv(v) for k, v in x.items()}
        if isinstance(x, list):
            return [conv(v) for v in x]
        return x
    return conv(raw)


# ── registry: name → (callable, JSON schema) ────────────────────────────────────────────
TOOLS: dict[str, tuple[Callable[..., dict], dict]] = {
    "get_cluster": (get_cluster, {"type": "object", "properties": {"cluster_id": {"type": "string"}}, "required": ["cluster_id"]}),
    "get_ledger_entry": (get_ledger_entry, {"type": "object", "properties": {"norad_id": {"type": "integer"}}, "required": ["norad_id"]}),
    "get_conjunction": (get_conjunction, {"type": "object", "properties": {"conj_id": {"type": "string"}}, "required": ["conj_id"]}),
    "simulate_action": (simulate_action, {"type": "object", "properties": {
        "cluster_id": {"type": "string"}, "target_id": {"type": ["integer", "null"]},
        "action": {"type": "string", "enum": ["HOLD", "MANEUVER", "WAIT", "OBSERVE"]},
        "dv_vector_mps": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "RTN frame, m/s"},
        "t_burn": {"type": ["string", "null"], "description": "ISO 8601 UTC"}, "wait_min": {"type": ["number", "null"], "description": "WAIT: minutes; give target_id too for WAIT-then-clear priced by VoI"},
        "horizon_h": {"type": "number", "default": 72}}, "required": ["cluster_id", "action"]}),
    "run_uncertainty_analysis": (run_uncertainty_analysis, {"type": "object", "properties": {
        "cluster_id": {"type": "string"}, "strategy_id": {"type": "string"}, "n_samples": {"type": "integer", "default": 100}},
        "required": ["cluster_id", "strategy_id"]}),
    "compute_voi": (compute_voi_tool, {"type": "object", "properties": {
        "conj_id": {"type": "string"}, "wait_options_min": {"type": ["array", "null"], "items": {"type": "number"}}}, "required": ["conj_id"]}),
    "rank_strategies": (rank_strategies, {"type": "object", "properties": {
        "cluster_id": {"type": "string"}, "strategy_ids": {"type": "array", "items": {"type": "string"}},
        "weights": {"type": ["object", "null"]}}, "required": ["cluster_id", "strategy_ids"]}),
    "validate_action": (validate_action, {"type": "object", "properties": {
        "target_id": {"type": "integer"}, "dv_vector_mps": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "t_burn": {"type": "string"}}, "required": ["target_id", "dv_vector_mps", "t_burn"]}),
    "evaluate_deployment": (evaluate_deployment, {"type": "object", "properties": {
        "n_satellites": {"type": "integer"}, "target_alt_km": {"type": "number"}, "inclination_deg": {"type": "number"},
        "alternatives_km": {"type": ["array", "null"], "items": {"type": "number"}}}, "required": ["n_satellites", "target_alt_km", "inclination_deg"]}),
}

DESCRIPTIONS = {
    "get_cluster": "Return a risk cluster: members, edges (conjunctions with Pc), keystone object, max-Pc object, whether they differ.",
    "get_ledger_entry": "Return one object's externality ledger entry.",
    "get_conjunction": "Return one conjunction with geometry, covariance source and Pc.",
    "simulate_action": "Apply a hypothetical action (HOLD / MANEUVER with an RTN Δv vector and burn epoch / WAIT / OBSERVE) and propagate forward. Returns the resulting conjunction set, Pc values and systemic cost. Does NOT validate feasibility.",
    "run_uncertainty_analysis": "Monte Carlo over the covariance for a simulated strategy. Returns expected cost, p95 cost, max regret and the safe fraction.",
    "compute_voi": "Value of information: expected cost reduction from delaying to acquire better tracking, net of the risk of delay.",
    "rank_strategies": "Score simulated strategies under the objective weights. Returns both the expected-value optimum and the minimax-regret optimum.",
    "validate_action": "Deterministic feasibility and safety check on a concrete proposed burn. May REJECT with a specific reason. Rejection is normal; incorporate the reason and re-propose.",
    "evaluate_deployment": "Evaluate a proposed constellation deployment across altitudes: burden, hazard, OCS, and whether the two optima disagree.",
}


def anthropic_tool_defs() -> list[dict]:
    return [{"name": n, "description": DESCRIPTIONS[n], "input_schema": schema} for n, (_, schema) in TOOLS.items()]


def call_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    fn, _ = TOOLS[name]
    started = datetime.now()
    try:
        out = fn(ctx, **args)
        ok = True
    except Exception as e:  # surfaced in the trace, never hidden (§14.5)
        out, ok = {"error": f"{type(e).__name__}: {e}"}, False
    ctx.calls.append({"tool": name, "args": args, "ok": ok, "result": out, "summary": _summarise(name, out),
                      "elapsed_s": (datetime.now() - started).total_seconds()})
    return out


def _summarise(name: str, out: dict) -> str:
    """One line per call for the trace view (S7); the full result stays in `result`."""
    def v(k):
        x = out.get(k)
        return x.get("value") if isinstance(x, dict) and "value" in x else x
    def f(k, fmt):
        x = v(k)
        return format(x, fmt) if isinstance(x, (int, float)) else "N/A"
    try:
        if "error" in out:
            return "ERROR " + out["error"]
        if name == "get_cluster":
            return f"{len(out['members'])} members · keystone {out['keystone_id']} · max-Pc {out['max_pc_object_id']}"
        if name == "get_conjunction":
            return f"Pc {f('pc', '.2e')} · miss {f('miss_distance_m', '.0f')} m · TCA {out['tca'][:16]}Z"
        if name == "simulate_action":
            return f"{out['strategy_id']} · Pc after {f('pc_max_after', '.2e')} · Δv {f('dv_mps', '.3f')} m/s · J {out['systemic_cost']:.3f}"
        if name == "run_uncertainty_analysis":
            return f"safe {f('safe_fraction', '.2f')} · E[J] {f('expected_cost', '.3f')} · p95 {f('p95_cost', '.3f')}"
        if name == "compute_voi":
            return f"act-now cost {f('cost_now', '.3f')} · recommended wait {out['recommended_wait_min']} min"
        if name == "rank_strategies":
            return f"EV {out['by_expected'][0]['strategy_id']} · regret {out['by_regret'][0]['strategy_id']}"
        if name == "validate_action":
            return f"{out['verdict']} {out.get('violated') or ''}".strip()
        if name == "get_ledger_entry":
            return f"imposed Δv {f('dv_imposed_mps', '.3f')} · CAB {f('cab', '.3f')}"
    except (KeyError, IndexError, TypeError):
        pass
    return str(out)[:80]
