"""SPEC §10.6 simulator, §10.7 optimiser, §10.8 VoI, §10.9 validator acceptance tests."""
import copy
from datetime import timedelta

import numpy as np
import pytest

from oci.config import CONFIG
from oci.data import synthetic as S
from oci.decide.optimize import evaluate, generate_strategies
from oci.decide.validate import validate
from oci.decide.voi import compute_voi
from oci.graph.build import build_graph
from oci.physics.maneuver import Burn, dv_to_clear
from oci.sim.simulate import Action, OrbitalState, simulate
from tests.conftest import objects_of


@pytest.fixture(scope="module")
def keystone(scenarios, screened):
    sc, res = scenarios["keystone_cluster"], screened["keystone_cluster"]
    objs = objects_of(sc)
    g = build_graph(res.conjunctions, objs)
    state = OrbitalState(objs, sc.window_start, frozenset(c.conj_id for c in res.conjunctions))
    return sc, res, objs, g.clusters[0], state


# ── M6 simulator ──────────────────────────────────────────────────────────────────────────
def test_simulator_is_pure(keystone):
    sc, res, objs, cluster, state = keystone
    before = {k: v for k, v in state.objects.items()}
    burn = Burn(cluster.keystone_id, (0.0, 0.2, 0.0), sc.window_start + timedelta(hours=3))
    a = simulate(state, Action("MANEUVER", target_id=burn.target_id, burn=burn), res.conjunctions)
    b = simulate(state, Action("MANEUVER", target_id=burn.target_id, burn=burn), res.conjunctions)
    assert state.objects == before
    assert [(c.key(), round(c.miss_m, 6)) for c in a.conjunctions] == [(c.key(), round(c.miss_m, 6)) for c in b.conjunctions]
    assert objs[burn.target_id] is state.objects[burn.target_id]


def test_hold_changes_nothing(keystone):
    sc, res, objs, cluster, state = keystone
    r = simulate(state, Action("HOLD"), res.conjunctions)
    assert {c.key() for c in r.conjunctions} == {c.key() for c in res.conjunctions}
    assert r.new_conj_ids == [] and r.dv_mps.value == 0.0


def test_maneuver_reduces_target_pc(keystone):
    sc, res, objs, cluster, state = keystone
    pc_star = CONFIG.thresholds.declared_pc_threshold
    c = max((x for x in res.conjunctions if x.pc.value), key=lambda x: x.pc.value)
    bearer = objs[c.primary_id] if objs[c.primary_id].is_maneuverable else objs[c.secondary_id]
    other = objs[c.secondary_id] if bearer.norad_id == c.primary_id else objs[c.primary_id]
    r = dv_to_clear(bearer, other, c.tca, pc_star)
    burn = Burn(bearer.norad_id, tuple((r.dv_mps.value if d == r.direction else 0.0) for d in "RTN"), r.t_burn)
    sim = simulate(state, Action("MANEUVER", target_id=bearer.norad_id, burn=burn), res.conjunctions)
    same_pair = [x for x in sim.conjunctions if x.key() == c.key() and abs((x.tca - c.tca).total_seconds()) < 600]
    assert not same_pair or all((x.pc.value or 0) < pc_star for x in same_pair)


def test_maneuver_can_create_new_conjunction(keystone):
    """If no burn in the grid ever creates a new conjunction, neighbourhood re-screening is too narrow."""
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions, include=("MANEUVER",))
    created = 0
    for s in strategies:
        sim = simulate(state, s.action, res.conjunctions)
        created += bool(sim.new_conj_ids)
    assert created >= 1


def test_mc_reproducible_with_seed(keystone):
    sc, res, objs, cluster, state = keystone
    s1 = generate_strategies(cluster, state, res.conjunctions, include=("HOLD", "MANEUVER"))[:4]
    s2 = generate_strategies(cluster, state, res.conjunctions, include=("HOLD", "MANEUVER"))[:4]
    a = evaluate(s1, cluster, state, res.conjunctions, n_mc=30, seed=5)
    b = evaluate(s2, cluster, state, res.conjunctions, n_mc=30, seed=5)
    assert [x.expected_cost.value for x in a.strategies] == [x.expected_cost.value for x in b.strategies]


# ── M7 optimiser ──────────────────────────────────────────────────────────────────────────
def test_weights_change_recommendation(keystone):
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions)
    safety_first = {"safety": 0.9, "future": 0.05, "fuel": 0.02, "mission": 0.02, "network": 0.01}
    fuel_first = {"safety": 0.05, "future": 0.05, "fuel": 0.45, "mission": 0.44, "network": 0.01}
    a = evaluate(copy.deepcopy(strategies), cluster, state, res.conjunctions, weights=safety_first, n_mc=0)
    b = evaluate(copy.deepcopy(strategies), cluster, state, res.conjunctions, weights=fuel_first, n_mc=0)
    assert a.by_expected[0].strategy_id != b.by_expected[0].strategy_id


def test_hold_wins_when_risk_negligible(scenarios, screened):
    """Inflate the miss distances → Pc ≪ Pc* everywhere → HOLD must be the optimum."""
    sc, res = scenarios["dead_rocket_body"], screened["dead_rocket_body"]
    objs = objects_of(sc)
    far = [c for c in res.conjunctions if c.miss_m > 3000]      # the 3.9 km approach only
    if not far:
        pytest.skip("no far approach in this scenario")
    g = build_graph(far, objs)
    state = OrbitalState(objs, sc.window_start, frozenset(c.conj_id for c in far))
    strategies = generate_strategies(g.clusters[0], state, far)
    r = evaluate(strategies, g.clusters[0], state, far, n_mc=0)
    assert r.by_expected[0].kind == "HOLD"


def test_cost_normalisation_bounded(keystone):
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions)[:8]
    r = evaluate(strategies, cluster, state, res.conjunctions, n_mc=0)
    for s in r.strategies:
        for term in ("safety", "future", "fuel", "mission", "network"):
            assert 0.0 <= getattr(s.cost, term) <= 1.0


def test_rankings_can_disagree(keystone):
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions)
    r = evaluate(strategies, cluster, state, res.conjunctions, n_mc=60, seed=42)
    heads = {r.by_expected[0].strategy_id, r.by_robust[0].strategy_id, r.by_regret[0].strategy_id}
    assert len(heads) >= 2


# ── M8 VoI ────────────────────────────────────────────────────────────────────────────────
def test_voi_positive_under_high_uncertainty(scenarios, screened):
    sc, res = scenarios["voi_event"], screened["voi_event"]
    v = compute_voi(res.conjunctions[0], objects_of(sc), sc.window_start, n_samples=150)
    assert v.recommended_wait_min is not None
    assert any(o.voi_net.value > 0 for o in v.options)


def test_voi_negative_when_lead_time_short(scenarios, screened):
    sc, res = scenarios["voi_event"], screened["voi_event"]
    c = res.conjunctions[0]
    late_epoch = c.tca - timedelta(minutes=150)          # barely one orbit + margins left
    v = compute_voi(c, objects_of(sc), late_epoch, wait_options_min=(60.0, 120.0), n_samples=100)
    assert v.recommended_wait_min is None
    assert all((not o.feasible) or o.voi_net.value <= 0 for o in v.options)


def test_voi_risk_terms_nonzero(scenarios, screened):
    sc, res = scenarios["voi_event"], screened["voi_event"]
    v = compute_voi(res.conjunctions[0], objects_of(sc), sc.window_start, n_samples=50)
    for o in v.options:
        assert o.risk_of_delay.assumptions["p_window_closes"] > 0.0


# ── M9 validator ──────────────────────────────────────────────────────────────────────────
def test_excessive_dv_rejected(keystone):
    sc, res, objs, cluster, state = keystone
    burn = Burn(cluster.keystone_id, (0.0, 5.0, 0.0), sc.window_start + timedelta(hours=3))
    v = validate(Action("MANEUVER", target_id=burn.target_id, burn=burn), state, res.conjunctions)
    assert v.status == "REJECTED" and "C1" in v.violated


def test_late_burn_rejected(keystone):
    sc, res, objs, cluster, state = keystone
    c = max((x for x in res.conjunctions if x.pc.value), key=lambda x: x.pc.value)
    tgt = c.primary_id if objs[c.primary_id].is_maneuverable else c.secondary_id
    burn = Burn(tgt, (0.0, 0.1, 0.0), c.tca - timedelta(minutes=10))
    v = validate(Action("MANEUVER", target_id=tgt, burn=burn), state, res.conjunctions)
    assert v.status == "REJECTED" and "C4" in v.violated


def test_valid_maneuver_approved(keystone):
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions, include=("MANEUVER",))
    approved = [s for s in strategies if validate(s.action, state, res.conjunctions).status == "APPROVED"]
    assert approved


def test_rejection_is_unscripted(keystone):
    """§10.9: with no hardcoded rejection, at least one generated strategy fails on constraint logic alone."""
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions)
    verdicts = [validate(s.action, state, res.conjunctions) for s in strategies if s.kind != "HOLD" and s.kind != "OBSERVE"]
    rejected = [v for v in verdicts if v.status == "REJECTED"]
    assert rejected
    assert any("C7" in v.violated for v in rejected)


def test_wait_eliminating_window_rejected(keystone):
    sc, res, objs, cluster, state = keystone
    c = min((x for x in res.conjunctions if x.pc.value and x.pc.value >= CONFIG.thresholds.declared_pc_threshold), key=lambda x: x.tca)
    lead = (c.tca - state.epoch).total_seconds() / 60.0
    v = validate(Action("WAIT", wait_min=lead - 20.0), state, res.conjunctions)
    assert v.status == "REJECTED" and "C4" in v.violated


def test_secondary_conjunction_rejected_with_norad_in_reason(keystone):
    sc, res, objs, cluster, state = keystone
    strategies = generate_strategies(cluster, state, res.conjunctions, include=("MANEUVER",))
    for s in strategies:
        v = validate(s.action, state, res.conjunctions)
        if "C7" in v.violated:
            assert "NORAD" in v.reason and any(str(n) in v.reason for n in cluster.members)
            return
    pytest.fail("no C7 rejection produced — re-screen neighbourhood may be too narrow")
