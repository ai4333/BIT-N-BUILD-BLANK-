"""SPEC §17.2 physics validation + §10.2 propagator + §11.2 manoeuvre tests."""
import math
from datetime import timedelta

import numpy as np
import pytest

from oci.config import MU_EARTH_KM3_S2, R_EARTH_KM
from oci.data import synthetic as S
from oci.data.objects import Elements, SpaceObject, derive_orbit
from oci.labels import Traced
from oci.physics.decay import decay_lifetime_years
from oci.physics.geometry import covariance_inertial, encounter_plane, rtn_basis
from oci.physics.maneuver import Burn, apply_maneuver, delta_sma_analytic_km, fit_mean_elements, rv2coe
from oci.physics.pc import compute_pc, dilution_flag, foster_2d
from oci.physics.propagate import PropagationError, propagate, propagate_batch, specific_energy, time_grid


def _obj(alt=550.0, inc=53.0):
    r, v = S.circular_state(alt, 10.0, 20.0, 90.0 - inc)
    return S.object_from_state(1, "T", r, v, S.T0, object_type="PAYLOAD", operator="OP",
                               is_active=True, is_maneuverable=True, sigma=S.SIGMA_ACTIVE)


# ── §11.1 derived quantities ──────────────────────────────────────────────────────────────
def test_period_from_mean_motion_roundtrip():
    el = Elements(S.T0, 15.5, 0.001, 53.0, 0, 0, 0)
    d = derive_orbit(el)
    a_from_period = (MU_EARTH_KM3_S2 * (d.period_min * 60 / (2 * math.pi)) ** 2) ** (1 / 3)
    assert abs(a_from_period - d.sma_km) / d.sma_km < 1e-6


# ── §10.2 propagator ─────────────────────────────────────────────────────────────────────
def test_position_sanity_leo():
    st = propagate(_obj(), S.T0 + timedelta(hours=3))
    assert 6700 < np.linalg.norm(st.r_km) < 7100


def test_error_code_raises():
    el = Elements(S.T0, 16.9, 0.0, 53.0, 0, 0, 0, bstar=0.9)   # violently decaying
    o = SpaceObject(2, "DEAD", "DEBRIS", False, False, "X", el)
    with pytest.raises(PropagationError):
        propagate(o, S.T0 + timedelta(days=30))


def test_energy_consistency_24h():
    o = _obj()
    s0, s1 = propagate(o, S.T0), propagate(o, S.T0 + timedelta(hours=24))
    e0, e1 = specific_energy(s0.r_km, s0.v_kmps), specific_energy(s1.r_km, s1.v_kmps)
    assert abs(e1 - e0) / abs(e0) < 1e-3          # SGP4 is not conservative; gross-bug smoke test


def test_batch_matches_single():
    o = _obj()
    ts = time_grid(S.T0, S.T0 + timedelta(hours=2), 30.0)
    r, v, e = propagate_batch([o], ts)
    for k, t in enumerate(ts):
        st = propagate(o, t)
        assert np.allclose(r[0, k], st.r_km, atol=1e-9)
        assert np.allclose(v[0, k], st.v_kmps, atol=1e-9)


@pytest.mark.timeout(120)
def test_batch_performance_10k_x_288():
    import time
    rng = np.random.default_rng(0)
    objs = []
    for i in range(10_000):
        alt = rng.uniform(400, 1200); a = R_EARTH_KM + alt
        n = math.sqrt(MU_EARTH_KM3_S2 / a ** 3) * 86400 / (2 * math.pi)
        objs.append(SpaceObject(10 + i, f"R{i}", "PAYLOAD", True, True, "OP",
                                Elements(S.T0, n, rng.uniform(0, 0.01), rng.uniform(0, 99), rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360))))
    ts = time_grid(S.T0, S.T0 + timedelta(hours=72), 15.0)
    assert len(ts) == 289
    t = time.perf_counter()
    propagate_batch(objs, ts)
    assert time.perf_counter() - t < 30.0


# ── §11.3 frames ─────────────────────────────────────────────────────────────────────────
def test_rtn_rotation_orthonormal():
    st = propagate(_obj(), S.T0)
    M = rtn_basis(st.r_km, st.v_kmps)
    assert np.allclose(M @ M.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(M) > 0


def test_covariance_rotation_preserves_trace():
    st = propagate(_obj(), S.T0)
    cov = covariance_inertial((40.0, 250.0, 35.0), st.r_km, st.v_kmps)
    assert abs(np.trace(cov) - (40 ** 2 + 250 ** 2 + 35 ** 2)) < 1e-8


# ── §11.2 manoeuvre and element rebuild ──────────────────────────────────────────────────
def test_zero_dv_roundtrips_elements():
    o = _obj()
    tb = S.T0 + timedelta(hours=2)
    o2 = apply_maneuver(o, Burn(1, (0.0, 0.0, 0.0), tb))
    for dt in (0, 1, 6, 24):
        a, b = propagate(o, tb + timedelta(hours=dt)), propagate(o2, tb + timedelta(hours=dt))
        assert np.linalg.norm(a.r_km - b.r_km) * 1000 < 0.05     # 5 cm over 24 h


def test_energy_after_impulsive_dv_matches_vis_viva():
    o = _obj()
    tb = S.T0 + timedelta(hours=1)
    st = propagate(o, tb)
    o2 = apply_maneuver(o, Burn(1, (0.0, 0.5, 0.0), tb))
    st2 = propagate(o2, tb)
    v_expected = st.v_kmps + rtn_basis(st.r_km, st.v_kmps).T @ np.array([0, 0.5e-3, 0])
    e_expected = np.dot(v_expected, v_expected) / 2 - MU_EARTH_KM3_S2 / np.linalg.norm(st.r_km)
    assert abs(specific_energy(st2.r_km, st2.v_kmps) - e_expected) / abs(e_expected) < 1e-9


def test_sma_change_matches_analytic():
    o = _obj()
    o2 = apply_maneuver(o, Burn(1, (0.0, 1.0, 0.0), S.T0 + timedelta(hours=1)))
    da = o2.orbit.sma_km - o.orbit.sma_km
    assert abs(da - delta_sma_analytic_km(o.orbit.sma_km, 1.0)) / abs(da) < 0.01
    assert 1.0 < da < 3.0    # "a few hundred metres to a couple of km per m/s" — the §11.2 anchor


# ── §11.4 Pc ────────────────────────────────────────────────────────────────────────────
def test_pc_against_monte_carlo():
    rng = np.random.default_rng(1)
    cov = np.array([[200.0 ** 2, 0.3 * 200 * 900], [0.3 * 200 * 900, 900.0 ** 2]])
    miss = np.array([150.0, -300.0]); hbr = 20.0
    pc = foster_2d(miss, cov, hbr)
    samples = rng.multivariate_normal([0, 0], cov, size=400_000)
    mc = np.mean(np.linalg.norm(samples - miss, axis=1) <= hbr)
    assert abs(pc - mc) < 4 * math.sqrt(mc * (1 - mc) / 400_000) + 1e-6


def test_pc_monotonic_in_miss_distance():
    cov = np.diag([100.0 ** 2, 500.0 ** 2])
    vals = [foster_2d(np.array([d, 0.0]), cov, 5.0) for d in (0, 50, 100, 200, 400, 800)]
    assert all(a > b for a, b in zip(vals, vals[1:]))


def test_pc_dilution_region_detected():
    cov = np.diag([50.0 ** 2, 50.0 ** 2])
    # Dilution: the miss sits inside the ellipse, so inflating σ LOWERS Pc — a low Pc there is
    # not reassuring. Far outside the ellipse, inflating σ raises Pc: not dilution.
    assert dilution_flag(np.array([10.0, 0.0]), cov, 5.0)
    assert not dilution_flag(np.array([400.0, 0.0]), cov, 5.0)


def test_pc_none_without_covariance():
    r = compute_pc(None, None, "none")
    assert r.pc.value is None and r.pc.na_reason
    assert r.pc_max.value is None


# ── §11.9.1 decay ───────────────────────────────────────────────────────────────────────
def test_decay_lifetime_ordering():
    life = [decay_lifetime_years(h, 0.01).value for h in (400, 500, 600, 700, 800, 900, 1000)]
    assert all(a < b or b >= 100.0 for a, b in zip(life, life[1:]))
    assert life[0] < 5 and life[-1] >= 50


def test_traced_na_requires_reason():
    with pytest.raises(ValueError):
        Traced(value=None, unit="m", label="COMPUTED", function="x")
