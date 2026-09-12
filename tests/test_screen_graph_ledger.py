"""SPEC §10.3 / §17.3 screening, §10.4 graph, §10.5 / §17.4 ledger acceptance tests."""
from datetime import timedelta

import numpy as np
import pytest

from oci.config import CONFIG
from oci.data import synthetic as S
from oci.graph.build import build_graph
from oci.ledger.compute import compute_ledger, sk_budget_mps_per_day
from oci.physics.maneuver import Burn, apply_maneuver, dv_to_clear
from oci.physics.screen import brute_force_screen, screen, screen_pair
from tests.conftest import objects_of


# ── screening ───────────────────────────────────────────────────────────────────────────
def test_synthetic_head_on_found(scenarios, screened):
    sc, res = scenarios["two_body_head_on"], screened["two_body_head_on"]
    assert len(res.conjunctions) == 1
    c = res.conjunctions[0]
    assert abs((c.tca - sc.expected["tca"]).total_seconds()) < 2.0
    assert abs(c.miss_m - sc.expected["miss_m"]) < 10.0


@pytest.mark.parametrize("name", ["keystone_cluster", "dead_rocket_body", "voi_event"])
@pytest.mark.parametrize("offset_min", [0.0, 0.11, 0.19])
def test_designed_conjunctions_found_at_any_phase(scenarios, name, offset_min):
    sc = scenarios[name]
    res = screen(sc.objects, sc.window_start + timedelta(minutes=offset_min), sc.window_end)
    found = {c.key() for c in res.conjunctions}
    for d in sc.designed:
        key = (min(d["primary"], d["secondary"]), max(d["primary"], d["secondary"]))
        assert key in found, f"missed designed {d}"


@pytest.mark.timeout(600)
def test_filter_chain_no_false_negatives():
    """§17.3: the single most important test. Brute force at 30 s must find nothing the chain misses."""
    rng = np.random.default_rng(7)
    from oci.data.objects import Elements, SpaceObject
    from oci.config import MU_EARTH_KM3_S2, R_EARTH_KM
    import math
    objs = []
    for i in range(120):
        alt = rng.uniform(540, 600); a = R_EARTH_KM + alt
        n = math.sqrt(MU_EARTH_KM3_S2 / a ** 3) * 86400 / (2 * math.pi)
        objs.append(SpaceObject(500 + i, f"R{i}", "PAYLOAD", True, True, "OP",
                                Elements(S.T0, n, rng.uniform(0, 0.001), rng.choice([53.0, 97.6, 87.9]) + rng.uniform(-0.2, 0.2),
                                         rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360))))
    t1 = S.T0 + timedelta(hours=12)
    d = 10_000.0
    chain = {c.key() for c in screen(objs, S.T0, t1, d_screen_m=d).conjunctions}
    brute = brute_force_screen(objs, S.T0, t1, d, step_min=0.5)
    assert brute <= chain, f"chain missed {brute - chain}"


@pytest.mark.parametrize("name", ["keystone_cluster", "dead_rocket_body"])
def test_coarse_gate_sufficient(scenarios, name):
    """Halving the step (7.5 s) finds no conjunction the default 15 s step missed."""
    sc = scenarios[name]
    a = {c.key() for c in screen(sc.objects, sc.window_start, sc.window_end).conjunctions}
    b = {c.key() for c in screen(sc.objects, sc.window_start, sc.window_end, coarse_min=0.125).conjunctions}
    assert b <= a


def test_intra_constellation_flagged():
    r, v = S.circular_state(550, 0, 0, 40)
    a = S.object_from_state(1, "STARLINK-1", r, v, S.T0, object_type="PAYLOAD", operator="SPACEX", is_active=True, is_maneuverable=True, sigma=S.SIGMA_ACTIVE)
    r2, v2 = S.crossing_state(r, v, 100.0, 300.0)
    b = S.object_from_state(2, "STARLINK-2", r2, v2, S.T0, object_type="PAYLOAD", operator="SPACEX", is_active=True, is_maneuverable=True, sigma=S.SIGMA_ACTIVE)
    cs = screen_pair(a, b, S.T0 - timedelta(minutes=10), S.T0 + timedelta(minutes=10))
    assert cs and cs[0].intra_constellation
    led = compute_ledger(cs, {1: a, 2: b}, 1.0)
    assert led.n_conjunctions_intra_excluded == 1 and not led.flows


def test_pc_none_when_no_covariance():
    r, v = S.circular_state(550, 0, 0, 40)
    a = S.object_from_state(1, "A", r, v, S.T0, object_type="PAYLOAD", operator="X", is_active=True, is_maneuverable=True, sigma=None)
    r2, v2 = S.crossing_state(r, v, 100.0, 300.0)
    b = S.object_from_state(2, "B", r2, v2, S.T0, object_type="DEBRIS", operator="Y", is_active=False, is_maneuverable=False, sigma=None)
    cs = screen_pair(a, b, S.T0 - timedelta(minutes=10), S.T0 + timedelta(minutes=10))
    assert cs[0].pc.value is None and cs[0].pc.na_reason and cs[0].covariance_source == "none"


def test_screening_deterministic(scenarios):
    sc = scenarios["keystone_cluster"]
    a = [(c.key(), round(c.miss_m, 6)) for c in screen(sc.objects, sc.window_start, sc.window_end).conjunctions]
    b = [(c.key(), round(c.miss_m, 6)) for c in screen(sc.objects, sc.window_start, sc.window_end).conjunctions]
    assert a == b


# ── graph ───────────────────────────────────────────────────────────────────────────────
def test_keystone_cluster_scenario(scenarios, screened):
    sc, res = scenarios["keystone_cluster"], screened["keystone_cluster"]
    g = build_graph(res.conjunctions, objects_of(sc))
    c = g.clusters[0]
    assert c.keystone_id == sc.expected["keystone_id"]
    assert set(c.max_pc_edge) == set(sc.expected["max_pc_edge"])
    assert c.disagreement is True
    assert g.weight_rule == "pc"


def test_centrality_matches_hand_computation(scenarios, screened):
    sc, res = scenarios["dead_rocket_body"], screened["dead_rocket_body"]
    g = build_graph(res.conjunctions, objects_of(sc))
    rb = 92000
    hand = sum(g.G.edges[rb, m]["w"] for m in g.G[rb])
    assert abs(g.centrality["wdegree"][rb] - hand) < 1e-12
    assert g.centrality["degree"][rb] == len(list(g.G[rb]))


# ── ledger ──────────────────────────────────────────────────────────────────────────────
def test_dead_rocket_body_scenario(scenarios, screened):
    sc, res = scenarios["dead_rocket_body"], screened["dead_rocket_body"]
    led = compute_ledger(res.conjunctions, objects_of(sc), 2.0)
    top = led.entries[0]
    assert top.norad_id == sc.expected["imposer"]
    assert top.maneuvers_forced.value >= 3
    assert top.operators_affected.value == sc.expected["operators_affected"]
    assert top.maneuvers_performed.value == 0 and top.dv_spent_mps.value == 0
    assert all(f.attribution_rule == "R1" for f in led.flows)
    assert led.share_of_dv_from_dead.value == 1.0


def test_dead_object_bears_nothing(scenarios, screened):
    for name in ("keystone_cluster", "dead_rocket_body"):
        led = compute_ledger(screened[name].conjunctions, objects_of(scenarios[name]), 2.0)
        for e in led.entries:
            if not e.is_maneuverable:
                assert e.maneuvers_performed.value == 0 and e.dv_spent_mps.value == 0


def test_attribution_conserves_total(scenarios, screened):
    led = compute_ledger(screened["dead_rocket_body"].conjunctions, objects_of(scenarios["dead_rocket_body"]), 2.0)
    imposed = sum(e.dv_imposed_mps.value or 0 for e in led.entries)
    borne = sum(e.dv_spent_mps.value or 0 for e in led.entries)
    assert abs(imposed - borne) < 1e-9


def test_threshold_sensitivity(scenarios, screened):
    objs = objects_of(scenarios["dead_rocket_body"])
    cache = {}
    counts = {}
    for th in (1e-4, 1e-5, 3e-7):
        led = compute_ledger(screened["dead_rocket_body"].conjunctions, objs, 2.0, pc_threshold=th, dv_cache=cache)
        e = led.entries[0]
        assert e.pc_threshold == th and e.field_name_maneuvers == f"maneuvers_forced_at_Pc_{th:g}"
        assert e.maneuvers_forced.assumptions["pc_threshold"] == th
        counts[th] = e.maneuvers_forced.value
    assert counts[1e-4] <= counts[1e-5] <= counts[3e-7]


def test_dv_reduces_pc(scenarios, screened):
    """§10.5: closes the loop — the computed Δv really clears the threshold on re-screen."""
    sc, res = scenarios["dead_rocket_body"], screened["dead_rocket_body"]
    objs = objects_of(sc)
    pc_star = CONFIG.thresholds.declared_pc_threshold
    checked = 0
    for c in res.conjunctions:
        if c.pc.value is None or c.pc.value < pc_star:
            continue
        bearer = objs[c.primary_id] if objs[c.primary_id].is_maneuverable else objs[c.secondary_id]
        other = objs[c.secondary_id] if bearer.norad_id == c.primary_id else objs[c.primary_id]
        r = dv_to_clear(bearer, other, c.tca, pc_star)
        assert r.dv_mps.value is not None and r.direction is not None
        moved = apply_maneuver(bearer, Burn(bearer.norad_id, tuple((r.dv_mps.value if d == r.direction else 0.0) for d in "RTN"), r.t_burn))
        after = screen_pair(moved, other, c.tca - timedelta(minutes=20), c.tca + timedelta(minutes=20), d_screen_m=50_000)
        worst = max((x.pc.value or 0 for x in after), default=0.0)
        assert worst < pc_star
        checked += 1
    assert checked >= 3


def test_mission_days_consistency(scenarios, screened):
    led = compute_ledger(screened["dead_rocket_body"].conjunctions, objects_of(scenarios["dead_rocket_body"]), 2.0)
    objs = objects_of(scenarios["dead_rocket_body"])
    for f in led.flows:
        if f.dv_mps:
            assert abs(f.mission_days * sk_budget_mps_per_day(objs[f.bearer_id].orbit.mean_alt_km) - f.dv_mps) < 1e-9


def test_ranking_differs_from_pc_mass_ranking(scenarios, screened):
    """§10.5 scientific self-check: the burden ranking is not the hazard (Pc×mass) ranking."""
    sc, res = scenarios["keystone_cluster"], screened["keystone_cluster"]
    objs = objects_of(sc)
    led = compute_ledger(res.conjunctions, objs, 1.5)
    burden = [e.norad_id for e in led.entries if (e.dv_imposed_mps.value or 0) > 0]
    hazard = {}
    for c in res.conjunctions:
        for nid in (c.primary_id, c.secondary_id):
            hazard[nid] = hazard.get(nid, 0.0) + (c.pc.value or 0.0) * objs[nid].mass_kg_est
    hz = [n for n, _ in sorted(hazard.items(), key=lambda kv: -kv[1])][: len(burden)]
    assert burden != hz


def test_every_ledger_number_is_traced(scenarios, screened):
    from oci.labels import Traced
    led = compute_ledger(screened["keystone_cluster"].conjunctions, objects_of(scenarios["keystone_cluster"]), 1.5)
    for e in led.entries:
        for f in ("conjunctions_generated", "maneuvers_forced", "dv_imposed_mps", "mission_days_imposed", "operators_affected",
                  "maneuvers_performed", "dv_spent_mps", "cab", "cab_normalised", "decay_lifetime_yr_est", "projected_lifetime_dv", "implied_fee_usd_yr"):
            t = getattr(e, f)
            assert isinstance(t, Traced)
            if t.value is None:
                assert t.na_reason
        assert e.implied_fee_usd_yr.label == "INDICATIVE"
        assert e.maneuvers_forced.label == "MODELLED"
