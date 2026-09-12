"""The end-to-end pipeline as a pure function (SPEC §8.1 principle 2, §16.4):

    detect → graph → ledger → strategies → simulate → compare → validate → explain

`run_pipeline(state)` has no hidden mutation, which is what makes Chaos Mode
`recommend(chaos(state))` rather than a retrofit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from oci.config import CONFIG
from oci.data.objects import SpaceObject
from oci.data.synthetic import Scenario, load
from oci.decide.optimize import OptimizeResult, Strategy, evaluate, generate_strategies
from oci.decide.validate import Verdict, validate
from oci.decide.voi import VoIResult, compute_voi
from oci.graph.build import Cluster, GraphResult, build_graph
from oci.ledger.compute import LedgerResult, compute_ledger
from oci.physics.screen import Conjunction, ScreeningResult, screen
from oci.sim.simulate import OrbitalState


@dataclass
class PipelineResult:
    scenario: str
    state: OrbitalState
    screening: ScreeningResult
    graph: GraphResult
    ledger: LedgerResult
    cluster: Optional[Cluster]
    voi: Optional[VoIResult]
    optimisation: Optional[OptimizeResult]
    verdicts: dict[str, Verdict]
    recommendation: Optional[Strategy]
    recommendation_regret: Optional[Strategy]
    rejected: list[Strategy]
    timings: dict[str, float] = field(default_factory=dict)


def run_on_state(state: OrbitalState, window_end: datetime, scenario_name: str = "state",
                 n_mc: int = 100, seed: int = 42, validate_all: bool = True) -> PipelineResult:
    timings: dict[str, float] = {}
    t = time.perf_counter()
    objs = state.objects
    scr = screen(list(objs.values()), state.epoch, window_end)
    timings["screen"] = time.perf_counter() - t

    t = time.perf_counter()
    graph = build_graph(scr.conjunctions, objs)
    timings["graph"] = time.perf_counter() - t

    t = time.perf_counter()
    window_days = (window_end - state.epoch).total_seconds() / 86400.0
    ledger = compute_ledger(scr.conjunctions, objs, window_days)
    timings["ledger"] = time.perf_counter() - t

    cluster = graph.clusters[0] if graph.clusters else None
    state = OrbitalState(objs, state.epoch, frozenset(c.conj_id for c in scr.conjunctions), state.horizon_h)
    voi = optim = None
    verdicts: dict[str, Verdict] = {}
    rec = rec_regret = None
    rejected: list[Strategy] = []
    if cluster:
        pc_star = CONFIG.thresholds.declared_pc_threshold
        cc = [c for c in scr.conjunctions if c.primary_id in cluster.members and c.secondary_id in cluster.members]
        crit = [c for c in cc if c.pc.value is not None and c.pc.value >= pc_star]
        t = time.perf_counter()
        if crit:
            voi = compute_voi(max(crit, key=lambda c: c.pc.value), objs, state.epoch, seed=seed)
        timings["voi"] = time.perf_counter() - t

        t = time.perf_counter()
        strategies = generate_strategies(cluster, state, scr.conjunctions)
        optim = evaluate(strategies, cluster, state, scr.conjunctions, n_mc=n_mc, seed=seed)
        timings["strategies"] = time.perf_counter() - t

        t = time.perf_counter()
        # validate in ranking order until an approved strategy is found (all if requested)
        for s in optim.by_expected:
            if s.kind == "HOLD" or s.kind == "OBSERVE":
                v = Verdict("APPROVED", "no burn to validate", [])
            else:
                v = validate(s.action, state, scr.conjunctions, sim=s.sim)
            verdicts[s.strategy_id] = v
            s.validator_verdict, s.validator_reason = v.status, v.reason
            if v.status == "REJECTED":
                rejected.append(s)
            elif rec is None:
                rec = s
                if not validate_all:
                    break
        for s in optim.by_regret:
            if s.strategy_id in verdicts and verdicts[s.strategy_id].status == "APPROVED":
                rec_regret = s
                break
        timings["validate"] = time.perf_counter() - t
    return PipelineResult(scenario_name, state, scr, graph, ledger, cluster, voi, optim, verdicts,
                          rec, rec_regret, rejected, timings)


def run_pipeline(scenario_name: str, n_mc: int = 100, seed: int = 42, validate_all: bool = True) -> PipelineResult:
    sc: Scenario = load(scenario_name, seed)
    state = OrbitalState({o.norad_id: o for o in sc.objects}, sc.window_start)
    return run_on_state(state, sc.window_end, scenario_name, n_mc, seed, validate_all)


# ── terminal report ──────────────────────────────────────────────────────────────────────

def _line(ch: str = "═", n: int = 78) -> str:
    return ch * n + "\n"


def render_report(r: PipelineResult) -> str:
    out = []
    A = CONFIG.assumptions_block()
    A["covariance_source"] = ", ".join(sorted({o.covariance_source for o in r.state.objects.values()}))
    out.append(_line())
    out.append(f" ORBITAL CAPACITY INTELLIGENCE — vertical slice · scenario {r.scenario}\n")
    out.append(_line())
    out.append(" ASSUMPTIONS  " + " │ ".join(f"{k}: {v}" for k, v in A.items() if k in
               ("covariance_source", "propagator", "screening_volume_m", "pc_method", "pc_threshold", "hard_body_radius_m", "horizon_h", "mc_samples")) + "\n")
    out.append(f"              intra-constellation excluded: {A['intra_constellation_excluded']} │ attribution: {A['attribution_rules']} │ weights: {A['weights']}\n")
    out.append(_line("─"))
    s = r.screening.run
    out.append(f" SCREENING  {s.n_objects} objects · window {s.window_start:%Y-%m-%d %H:%M} → {s.window_end:%m-%d %H:%M}Z · "
               f"pairs {s.n_pairs_total} → stage1 {s.n_pairs_after_stage1} → index {s.n_pairs_after_stage2} → dips {s.n_candidates_stage3} → "
               f"conjunctions {s.n_conjunctions} · step {s.coarse_step_min*60:.0f} s · gate k={s.gate_k:.1f} · {s.runtime_s:.2f} s\n")
    for c in r.screening.conjunctions:
        pc = f"{c.pc.value:.2e}" if c.pc.value is not None else f"N/A ({c.pc.na_reason})"
        out.append(f"   {c.primary_id}–{c.secondary_id}  TCA {c.tca:%m-%d %H:%M:%S}Z  miss {c.miss_m:7.1f} m  v_rel {float(c.rel_speed_mps.value)/1000:5.2f} km/s  "
                   f"Pc {pc}  Pc_max {c.pc_max.value:.2e}  {c.pair_class}{'  DILUTION' if c.dilution else ''}\n")
    out.append(_line("─"))
    g = r.graph
    out.append(f" GRAPH  {g.G.number_of_nodes()} nodes · {g.G.number_of_edges()} edges · weight rule {g.weight_rule} · {len(g.clusters)} cluster(s)\n")
    for c in g.clusters:
        flag = "  ⚠ KEYSTONE ≠ MAX-Pc OBJECT" if c.disagreement else ""
        out.append(f"   {c.cluster_id}: members {c.members} · keystone {c.keystone_id} [{c.keystone_selected_by}, Σw={c.keystone_score:.2e}] · "
                   f"max-Pc edge {c.max_pc_edge} ({c.max_pc:.2e}) → object {c.max_pc_object_id} · critical {c.critical_conjunctions}{flag}\n")
    out.append(_line("─"))
    L = r.ledger
    out.append(f" EXTERNALITY LEDGER  window {L.window_days:.1f} d · Pc* = {L.pc_threshold:g} (IADC) · {L.n_conjunctions_used} conjunctions used, "
               f"{L.n_conjunctions_intra_excluded} intra-constellation excluded · share of Δv imposed by DEAD objects: {L.share_of_dv_from_dead.fmt(2)}\n")
    out.append(f"   {'#':>2} {'OBJECT':16s} {'TYPE':11s} {'ALT':>6s} {'CONJ':>4s} {'MNVR':>5s} {'Δv IMPOSED':>12s} {'DAYS':>6s} {'OPS':>3s} {'TOP BEARER':11s} "
               f"{'GINI':>5s} {'BORNE':>7s} {'LIFE':>6s} {'PROJ Δv':>8s} {'FEE/yr':>10s}\n")
    for e in L.entries:
        out.append(f"   {e.rank_by_dv_imposed:>2} {e.object_name[:16]:16s} {e.object_type[:11]:11s} {e.mean_alt_km:>6.0f} {int(e.conjunctions_generated.value):>4d} "
                   f"{e.maneuvers_forced.value:>5.1f} {e.dv_imposed_mps.fmt():>12s} {e.mission_days_imposed.value:>6.1f} {int(e.operators_affected.value):>3d} "
                   f"{(e.top_bearer or '—')[:11]:11s} {(f'{e.bearer_gini.value:.2f}' if e.bearer_gini.value is not None else '—'):>5s} "
                   f"{e.dv_spent_mps.value:>5.2f}{'*' if not e.is_maneuverable else ' '} {e.decay_lifetime_yr_est.value:>6.1f} {e.projected_lifetime_dv.value:>8.1f} "
                   f"{('$' + f'{e.implied_fee_usd_yr.value/1000:.0f}k' if e.implied_fee_usd_yr.value is not None else '—'):>10s}\n")
    out.append("   * = cannot manoeuvre (bears nothing by construction) · MNVR/Δv/DAYS/LIFE/PROJ are MODELLED · FEE is INDICATIVE\n")
    if r.cluster:
        out.append(_line("─"))
        c = r.cluster
        out.append(f" EVENT CONSOLE  cluster {c.cluster_id} · keystone {c.keystone_id} · max-Pc object {c.max_pc_object_id}{'  ⚠ differ' if c.disagreement else ''}\n")
        if r.voi and r.voi.options:
            v = r.voi
            out.append(f"   VoI on {v.conj_id} (cov {v.covariance_source}): act now costs {v.cost_now.fmt(3)} (Δv {v.dv_now_mps.fmt(3)})\n")
            for o in v.options:
                out.append(f"     wait {o.wait_min:4.0f} min → σ −{o.expected_sigma_reduction.value*100:4.1f}%  E[Pc] {o.expected_pc.value:.2e}  "
                           f"E[Δv] {o.expected_dv_mps.value:.3f} m/s  risk-of-delay {o.risk_of_delay.value:.3f}  VoI {o.voi_net.value:+.3f}{'' if o.feasible else '  (infeasible: window)'}\n")
            out.append(f"   → recommended wait: {v.recommended_wait_min if v.recommended_wait_min is not None else 'none (act now)'} \n")
        if r.optimisation:
            O = r.optimisation
            out.append(f"   STRATEGIES ({len(O.strategies)}, weights {O.weights_used})\n")
            out.append(f"   {'ID':18s} {'ACTION':58s} {'Pc after':>9s} {'FUT':>3s} {'Δv':>6s} {'J':>6s} {'E[J]':>6s} {'p95':>6s} {'REGRET':>6s} {'SAFE':>5s}  VERDICT\n")
            for s in O.by_expected:
                vd = r.verdicts.get(s.strategy_id)
                out.append(f"   {s.strategy_id:18s} {s.action.describe()[:58]:58s} {s.pc_after.value:>9.2e} {int(s.future_conjunctions.value):>3d} "
                           f"{s.dv_mps.value:>6.3f} {s.systemic_cost.value:>6.3f} {s.expected_cost.value:>6.3f} {s.p95_cost.value:>6.3f} {s.max_regret.value:>6.3f} "
                           f"{(f'{s.mc_safe_fraction.value:.2f}' if s.mc_safe_fraction.value is not None else '—'):>5s}  {vd.status if vd else '—'}\n")
            out.append(f"   EV optimum: {O.by_expected[0].strategy_id} · robust (p95): {O.by_robust[0].strategy_id} · minimax regret: {O.by_regret[0].strategy_id} · "
                       f"{'agree' if O.by_expected[0] is O.by_regret[0] else 'DISAGREE'}\n")
        if r.rejected:
            out.append(f"   REJECTED ({len(r.rejected)}):\n")
            for s in r.rejected:
                out.append(f"     {s.strategy_id}: {s.action.describe()}\n       → {s.validator_reason}\n")
        if r.recommendation:
            s = r.recommendation
            vd = r.verdicts[s.strategy_id]
            out.append(_line("─"))
            out.append(f" RECOMMENDATION: {s.action.describe()}\n")
            out.append(f"   WHY: lowest expected systemic cost among validated strategies (E[J] = {s.expected_cost.value:.3f}; HOLD = "
                       f"{next((x.expected_cost.value for x in O.strategies if x.kind == 'HOLD'), float('nan')):.3f}) [source: rank_strategies]\n")
            out.append(f"        post-action max Pc {s.pc_after.value:.2e} vs Pc* {CONFIG.thresholds.declared_pc_threshold:g}; {int(s.future_conjunctions.value)} conjunction(s) above threshold remain in {CONFIG.decision.horizon_h:.0f} h [source: simulate_action]\n")
            out.append(f"   TRADE-OFFS: Δv {s.dv_mps.value:.3f} m/s; mission impact {s.mission_impact.value:.2f} (normalised)\n")
            if s.mc_safe_fraction.value is not None:
                out.append(f"   CONFIDENCE BASIS: {s.mc_safe_fraction.value*100:.0f} of 100 sampled uncertainty scenarios remained below threshold under the declared covariance — "
                           f"NOT a prediction accuracy [source: run_uncertainty_analysis]\n")
            out.append(f"   VALIDATOR: {vd.status} — " + "; ".join(f"{c.id} {'✓' if c.passed else '✗'}" for c in vd.checks) + "\n")
            if r.recommendation_regret and r.recommendation_regret is not r.recommendation:
                out.append(f"   NOTE: the minimax-regret optimum is {r.recommendation_regret.strategy_id} ({r.recommendation_regret.action.describe()}); "
                           f"a single-satellite operator may prefer it.\n")
            out.append(f"   ASSUMPTIONS THAT MATTER: Pc threshold {CONFIG.thresholds.declared_pc_threshold:g}; covariance {A['covariance_source']}; HBR {CONFIG.pc.hard_body_radius_m} m (MODELLED)\n")
    out.append(_line("─"))
    out.append(" TIMINGS  " + " · ".join(f"{k} {v:.1f}s" for k, v in r.timings.items()) + "\n")
    out.append(_line())
    return "".join(out)
