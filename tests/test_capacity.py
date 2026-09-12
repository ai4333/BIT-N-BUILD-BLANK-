"""SPEC §10.10 M10 capacity engine acceptance tests. All offline; the population for the
two-peaks and decay tests is synthetic with the published structure (dense active traffic at
500–600 km, heavy inactive mass near 800–850 km), built from random circular elements."""
import math
from datetime import timedelta

import numpy as np
import pytest

from oci.capacity.deployment import DeploymentRequest, evaluate_deployment
from oci.capacity.flux import calibrate, shell_flux
from oci.capacity.ocs import compute_capacity, estimate_kappa, ocs_from_burden
from oci.capacity.shells import mean_relative_speed_kms, partition
from oci.config import CONFIG, MU_EARTH_KM3_S2, R_EARTH_KM
from oci.data.objects import Elements, SpaceObject, mass_model
from oci.data.synthetic import T0, load
from oci.physics.screen import screen
from oci.sim.simulate import OrbitalState


def _obj(nid, alt_km, inc_deg, raan, ma, otype, active, rng, operator="OPERATOR-X", rcs="MEDIUM"):
    a = R_EARTH_KM + alt_km
    n = math.sqrt(MU_EARTH_KM3_S2 / a ** 3) * 86400.0 / (2 * math.pi)
    el = Elements(epoch=T0, mean_motion_rev_day=n, eccentricity=0.0005, inclination_deg=inc_deg, raan_deg=raan,
                  argp_deg=float(rng.uniform(0, 360)), mean_anomaly_deg=ma, bstar=0.0, mean_motion_dot=0.0, mean_motion_ddot=0.0)
    mm = mass_model(otype, rcs)
    return SpaceObject(norad_id=nid, object_name=f"POP-{nid}", object_type=otype, is_active=active, is_maneuverable=active,
                       operator=operator, elements=el, source="synthetic", sigma_rtn_m=(60.0, 400.0, 50.0), covariance_source="declared", **mm)


def population(seed=1):
    """~600 objects: 300 active at 500–600 km (two operators, uncoordinated), 200 inactive large
    objects at 780–880 km, a thin background elsewhere."""
    rng = np.random.default_rng(seed)
    objs, nid = [], 100000
    for _ in range(300):
        objs.append(_obj(nid, rng.uniform(500, 600), rng.choice([53.0, 70.0, 97.6]), rng.uniform(0, 360), rng.uniform(0, 360), "PAYLOAD", True, rng,
                         operator=rng.choice(["OPERATOR-A", "OPERATOR-B"]))); nid += 1
    for _ in range(200):
        objs.append(_obj(nid, rng.uniform(780, 880), rng.choice([71.0, 82.9, 98.5]), rng.uniform(0, 360), rng.uniform(0, 360),
                         rng.choice(["ROCKET_BODY", "DEBRIS", "PAYLOAD"]), False, rng, operator="UNKNOWN-OPERATOR", rcs="LARGE")); nid += 1
    for _ in range(100):
        objs.append(_obj(nid, rng.uniform(300, 1200), rng.uniform(30, 100), rng.uniform(0, 360), rng.uniform(0, 360), "DEBRIS", False, rng,
                         operator="UNKNOWN-OPERATOR", rcs="SMALL")); nid += 1
    return objs


@pytest.fixture(scope="module")
def pop():
    return population()


@pytest.fixture(scope="module")
def screened(pop):
    """Screen the 500–600 km traffic for 24 h so q and the calibration factor are measured."""
    sub = [o for o in pop if 500 <= o.orbit.mean_alt_km < 600]
    res = screen(sub, T0, T0 + timedelta(hours=24))
    return sub, res


def test_ocs_bounded():
    for m in (-5.0, 0.0, 60.0, 120.0, 1e6):
        v = ocs_from_burden(m).value
        assert 0.0 <= v <= 100.0
    assert ocs_from_burden(None).value is None and ocs_from_burden(None).na_reason


def test_ocs_anchor_documented():
    t = ocs_from_burden(12.0)
    assert t.assumptions["m_viability_per_sat_yr"] == CONFIG.capacity.m_viability_per_sat_yr == 120.0
    assert "10 CAMs/month" in t.assumptions["anchor"]


def test_relative_speed_is_leo_like():
    v = mean_relative_speed_kms([53.0, 53.0, 70.0, 97.6, 98.0, 45.0], 550.0)
    assert 5.0 < v < 14.0
    assert mean_relative_speed_kms([53.0, 53.0], 550.0) > 0.0          # same inclination, random nodes still cross


def test_spatial_density_in_leo_range(pop):
    shells = [s for s in partition(pop) if s.n_objects > 10]
    for s in shells:
        assert 1e-11 < s.spatial_density_per_km3 < 1e-6


def test_flux_calibrates_against_pairwise(screened):
    sub, res = screened
    shells = [s for s in partition(sub) if s.n_objects]
    window_days = 1.0
    assert len(res.conjunctions) >= 20, "population too sparse for a calibration"
    factors = []
    for s in shells:
        cal = calibrate(s, res.conjunctions, {o.norad_id: o for o in sub}, window_days, 1e-4)
        if cal.n_conjunctions < 5:
            continue
        fl = shell_flux(s, 1e-4, cal, q_fallback=1e-3, c_intra=1.0)
        f = fl.calibration_factor.value
        assert f is not None
        factors.append(f)
        print(f"{s.shell_id}: pairwise {cal.conjunctions_per_object_year:.1f}/obj-yr vs flux {fl.conjunctions_per_sat_yr.value:.1f} → factor {f:.2f}")
    assert factors
    # the two engines agree within a stated factor of 3 — reported in the Traced assumptions, never tuned
    assert all(1 / 3 <= f <= 3 for f in factors), factors


def test_intra_constellation_factor_matters(pop):
    cap = compute_capacity(pop, pc_threshold=1e-4)
    d05 = evaluate_deployment(cap, DeploymentRequest(5000, 550, 53.0, c_intra=0.05))
    d10 = evaluate_deployment(cap, DeploymentRequest(5000, 550, 53.0, c_intra=1.0))
    m05, m10 = d05.baseline.maneuver_burden_per_sat_yr.value, d10.baseline.maneuver_burden_per_sat_yr.value
    assert m10 > 3.0 * m05, (m05, m10)
    assert d05.uncoordinated_comparison["maneuver_burden_per_sat_yr"].value == pytest.approx(m10)


def test_decay_included(pop):
    cap = compute_capacity(pop, pc_threshold=1e-4)
    with_decay = evaluate_deployment(cap, DeploymentRequest(2000, 550, 53.0, include_decay=True))
    without = evaluate_deployment(cap, DeploymentRequest(2000, 550, 53.0, include_decay=False))
    rank_with = [a.alt_km for a in sorted([with_decay.baseline] + with_decay.alternatives, key=lambda a: a.hazard_rank)]
    rank_without = [a.alt_km for a in sorted([without.baseline] + without.alternatives, key=lambda a: a.hazard_rank)]
    assert rank_with != rank_without
    assert with_decay.hazard_optimal_alt_km == min(with_decay.request.alternatives_km)   # lower self-cleans faster


def test_two_peaks_reproduced(pop):
    cap = compute_capacity(pop, pc_threshold=1e-4)
    assert cap.peaks_differ is True
    assert 450 <= cap.workload_peak_alt_km <= 625
    assert 750 <= cap.hazard_peak_alt_km <= 900
    d = evaluate_deployment(cap, DeploymentRequest(5000, 550, 53.0))
    assert d.optima_disagree and d.workload_optimal_alt_km != d.hazard_optimal_alt_km
    assert "no single optimum" in d.explanation


def test_no_bare_numbers_in_shell_rows(pop):
    from oci.labels import Traced
    cap = compute_capacity(pop, pc_threshold=1e-4)
    row = cap.shells[0].row()
    for k in ("spatial_density", "maneuver_burden_per_sat_yr", "ocs", "hazard_index", "decay_lifetime_yr", "kappa"):
        assert isinstance(row[k], Traced)
    assert row["kappa"].value is None and row["kappa"].na_reason      # not estimated → explicit N/A, not zero


def test_kappa_bounds():
    """κ ≥ 0; κ on the sparse (substitutes) shell < κ on the dense (complements) shell."""
    out = {}
    for name in ("substitutes_shell", "complements_shell"):
        sc = load(name)
        objs = {o.norad_id: o for o in sc.objects}
        res = screen(sc.objects, sc.window_start, sc.window_end)
        state = OrbitalState(objs, sc.window_start, frozenset(c.conj_id for c in res.conjunctions))
        sh = next(s for s in partition(sc.objects) if s.n_objects)
        k = estimate_kappa(sh, state, res.conjunctions, 1e-4, k_samples=4)
        assert k.kappa.value is not None and k.kappa.value >= 0.0
        out[name] = k
    assert out["substitutes_shell"].kappa.value < out["complements_shell"].kappa.value
    assert out["substitutes_shell"].regime == "SUBSTITUTES" and out["complements_shell"].regime == "COMPLEMENTS"


def test_agent_tool_evaluate_deployment():
    from oci.agent.tools import ToolContext, call_tool
    from oci.graph.build import build_graph
    sc = load("keystone_cluster")
    objs = {o.norad_id: o for o in sc.objects}
    res = screen(sc.objects, sc.window_start, sc.window_end)
    ctx = ToolContext(OrbitalState(objs, sc.window_start, frozenset(c.conj_id for c in res.conjunctions)), res.conjunctions, build_graph(res.conjunctions, objs), None)
    out = call_tool(ctx, "evaluate_deployment", {"n_satellites": 1000, "target_alt_km": 560, "inclination_deg": 53.0, "alternatives_km": [520, 560, 600]})
    assert "error" not in out and out["two_peaks_finding"]["optima_disagree"] in (True, False)
    assert out["baseline"]["ocs"]["label"] == "MODELLED"
